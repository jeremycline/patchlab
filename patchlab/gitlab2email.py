# SPDX-License-Identifier: GPL-2.0-or-later
"""
This module deals with turning Gitlab objects (merge requests, comments) into
emails.
"""
from email import message_from_string, utils as email_utils
import logging
import re
import textwrap
import time
import urllib

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.mail.utils import DNS_NAME
from patchwork import parser as patchwork_parser
from patchwork.models import Submission
import gitlab as gitlab_module

from patchlab.models import GitForge, BridgedSubmission, Branch


_log = logging.getLogger(__name__)

PREFIX_RE = re.compile(r"^\[.*\]")

#: The template used when the number of commits in a merge request exceed
#: :data:`settings.PATCHLAB_MAX_EMAILS`. Instead of sending the patches, send
#: instructions on how to get the git branch.
BIG_EMAIL_TEMPLATE = """{description}
Note:

The patch series is too large to sent by email.

To review the series locally, set up your repository to fetch from the GitLab
remote:

  $ git remote add gitlab {remote_url}
  $ git config remote.gitlab.fetch '+refs/merge-requests/*/head:refs/remotes/gitlab/merge-requests/*'
  $ git fetch gitlab

Finally, check out the merge request:

  $ git checkout gitlab/merge-requests/{merge_id}

It is also possible to review the merge request on GitLab at:
    {merge_url}
"""  # noqa: E501


def email_merge_request(
    gitlab: gitlab_module.Gitlab, forge_id: int, merge_id: int
) -> None:
    """Email a merge request to a mailing list."""
    try:
        git_forge = GitForge.objects.get(
            host=urllib.parse.urlsplit(gitlab.url).hostname, forge_id=forge_id
        )
    except GitForge.DoesNotExist:
        _log.error(
            "Request to bridge merge id %d from project id %d on %s cannot "
            "be handled as no git forge is configured in Patchlab's database.",
            merge_id,
            forge_id,
            urllib.parse.urlsplit(gitlab.url).hostname,
        )
        return
    project = gitlab.projects.get(forge_id)
    merge_request = project.mergerequests.get(merge_id)

    if _ignore(git_forge, merge_request):
        return

    # This is all pretty hacky, but works for now. Just hang out until the
    # pipeline is completed.
    initial_head = merge_request.sha
    if settings.PATCHLAB_PIPELINE_SUCCESS_REQUIRED:
        for _ in range(settings.PATCHLAB_PIPELINE_MAX_WAIT):
            if merge_request.head_pipeline["status"] not in ("failed", "success"):
                _log.info(
                    "Pipeline for %r is %s, checking back in a minute",
                    merge_request,
                    merge_request.head_pipeline["status"],
                )
                time.sleep(60)
            else:
                break
            merge_request = project.mergerequests.get(merge_id)
        else:
            _log.warn(
                "Pipeline failed to complete after %d minutes; not emailing %r",
                settings.PATCHLAB_PIPELINE_WAIT,
                merge_request,
            )
            return

    merge_request = project.mergerequests.get(merge_id)
    if initial_head != merge_request.sha:
        _log.info(
            "A new revision for %r has been pushed, skipping emailing revision %s",
            merge_request,
            initial_head,
        )
        return
    if _ignore(git_forge, merge_request):
        # A label might have been added or something while we waited for CI.
        return

    emails = _prepare_emails(gitlab, git_forge, project, merge_request)
    with get_connection(fail_silently=False) as conn:
        for email in emails:
            try:
                submission = _record_bridging(git_forge.project.listid, merge_id, email)
            except ValueError:
                # This message is already in the database, skip sending it
                continue
            email.connection = conn
            try:
                email.send(fail_silently=False)
            except Exception as e:
                # We were unable to send the email, delete it from the submission db
                # and raise the exception so we try again
                submission.delete()
                raise e


def _ignore(git_forge, merge_request):
    if merge_request.work_in_progress:
        _log.info("Not emailing %r because it's a work in progress", merge_request)
        return True
    if merge_request.merge_status == "cannot_be_merged":
        _log.info("Not emailing %r because it can't be merged", merge_request)
        return True
    if (
        settings.PATCHLAB_PIPELINE_SUCCESS_REQUIRED
        and merge_request.head_pipeline["status"] == "failed"
    ):
        _log.info("Not emailing %r as the test pipeline failed", merge_request)
        return True
    if "From email" in merge_request.labels:
        _log.info("Not emailing %r as it's from email to start with", merge_request)
        return True
    for label in settings.PATCHLAB_IGNORE_GITLAB_LABELS:
        if label in merge_request.labels:
            _log.info(
                "Not emailing %r as it is labeled with the %s label, which is ignored.",
                merge_request,
                label,
            )
            return True
    if BridgedSubmission.objects.filter(
        git_forge=git_forge, merge_request=merge_request.iid, commit=merge_request.sha
    ).first():
        _log.info(
            "Not emailing %r as the head sha is %s, which we already bridged.",
            merge_request,
            merge_request.sha,
        )
        return True

    return False


def _reroll(git_forge, merge_request):
    """Determine the patch reroll count based on previous submissions."""
    prior_submissions = BridgedSubmission.objects.filter(
        git_forge=git_forge, merge_request=merge_request.iid
    )
    latest_submission = prior_submissions.order_by("-series_version").first()
    if latest_submission is None:
        version = 1
        in_reply_to = None
    else:
        if latest_submission.series_version:
            version = latest_submission.series_version + 1
        else:
            version = 1
        in_reply_to = latest_submission.submission.msgid

    return version, in_reply_to


def _merge_request_ccs(git_forge, merge_request):
    """Collect merge request Ccs"""
    ccs = []
    if merge_request.description is not None:
        for line in merge_request.description.splitlines():
            cc_match = re.search(r"^\s*Cc:\s+(.*)$", line)
            if cc_match:
                ccs += cc_match.groups()

    ccs += [line[3:].strip() for line in merge_request.labels if line.startswith("Cc:")]
    return _clean_ccs(ccs)


def _commit_ccs(commit):
    ccs = [commit.author_email]
    for line in commit.message.splitlines():
        cc_match = re.search(r"^\s*(Cc|Signed-off-by|Reviewed-by):\s+(.*)$", line)
        if cc_match and cc_match.group(2).strip():
            ccs.append(cc_match.group(2).strip())

    return _clean_ccs(ccs)


def _clean_ccs(ccs):
    ccs = [email_utils.parseaddr(cc)[1] for cc in ccs if email_utils.parseaddr(cc)[1]]
    ccs = list(
        set(
            [
                cc
                for cc in ccs
                if re.search(settings.PATCHLAB_CC_FILTER, cc, flags=re.IGNORECASE)
            ]
        )
    )
    ccs.sort()
    return ccs


def _prepare_emails(gitlab, git_forge, project, merge_request):
    """Prepare a set of emails that represent the given merge request."""
    try:
        branch = Branch.objects.get(
            git_forge=git_forge, name=merge_request.target_branch
        )
    except Branch.DoesNotExist:
        # Branch isn't configured to be bridged, skip.
        _log.info(
            "There is no branch in the patchlab database for %s; skipping",
            merge_request.target_branch,
        )
        return []

    from_email = settings.PATCHLAB_FROM_EMAIL.format(
        forge_user=merge_request.author["username"]
    )
    commits = list(reversed(list(merge_request.commits())))
    num_commits = len(commits)
    series_version, in_reply_to = _reroll(git_forge, merge_request)
    version_prefix = f"v{series_version}" if series_version > 1 else ""

    ccs = _merge_request_ccs(git_forge, merge_request)

    emails = []
    if num_commits > 1:
        # Compose a cover letter based on the pull request description.
        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
            "X-Patchlab-Series-Version": series_version,
        }
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to

        # We have to wrap each line rather than just using plain textwrap.fill
        # on the whole description as doing so destroys paragraphs and wraps
        # any Ccs into a sentence, which isn't what we want.
        if merge_request.description is not None:
            wrapped_description = "\n".join(
                [
                    textwrap.fill(line, width=72, replace_whitespace=False)
                    for line in merge_request.description.splitlines()
                ]
            )
        else:
            wrapped_description = "The merge request had no description."
        body = (
            f"From: {merge_request.author['username']} on {git_forge.host}\n\n"
            f"{wrapped_description}\n"
        )
        subject = (
            f"[{branch.subject_prefix} PATCH{version_prefix} 0/{num_commits}] "
            f"{' '.join(merge_request.title.splitlines())}"  # No multi-line headers allowed
        )
        cover_letter = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[git_forge.project.listemail],
            cc=ccs,
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )

        if num_commits > settings.PATCHLAB_MAX_EMAILS:
            cover_letter.body = BIG_EMAIL_TEMPLATE.format(
                description=body or "No description provided for merge request.",
                remote_url=f"{project.web_url}.git",
                merge_id=merge_request.iid,
                merge_url=merge_request.web_url,
            )
            return [cover_letter]

        in_reply_to = headers["Message-ID"]
        emails.append(cover_letter)

    for i, commit in enumerate(commits, 1):
        # This currently only works for public projects; authenticating with a
        # token does not work.
        # https://gitlab.com/gitlab-org/gitlab/issues/26228
        response = gitlab.session.get(f"{project.web_url}/commit/{commit.id}.patch")
        response.raise_for_status()
        patch = message_from_string(response.text)

        patch_num = "" if len(commits) == 1 else f" {str(i)}/{num_commits}"
        sanitized_patch_title = " ".join(commit.title.splitlines())
        subject = (
            f"[{branch.subject_prefix} PATCH{version_prefix}{patch_num}] "
            f"{sanitized_patch_title}"
        )
        patch_author = patch["From"]
        patch_ccs = sorted(list(set(_commit_ccs(commit) + ccs)))
        # Ensure anyone getting Cc'd on a patch also gets the cover letter
        if num_commits > 1:
            emails[0].cc = sorted(list(set(emails[0].cc + patch_ccs)))

        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Patch-Author": patch_author,
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
            "X-Patchlab-Commit": f"{commit.id}",
            "X-Patchlab-Series-Version": series_version,
        }
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to

        email = EmailMessage(
            subject=subject,
            body=f"From: {patch_author}\n\n{patch.get_payload()}",
            from_email=from_email,
            to=[git_forge.project.listemail],
            cc=patch_ccs,
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )
        emails.append(email)

    return emails


def email_comment(gitlab, forge_id, author, comment, merge_id=None) -> None:
    """Email a comment made on Gitlab"""
    try:
        git_forge = GitForge.objects.get(
            host=urllib.parse.urlsplit(gitlab.url).hostname, forge_id=forge_id
        )
    except GitForge.DoesNotExist:
        _log.error(
            "Got comment event for project id %d, which isn't in the database", forge_id
        )
        return

    commit = comment.get("commit_id")
    try:
        bridged_submission = BridgedSubmission.objects.filter(
            git_forge=git_forge
        ).order_by("-series_version")
        if merge_id:
            bridged_submission = bridged_submission.filter(merge_request=merge_id)
        if commit:
            bridged_submission = bridged_submission.filter(commit=commit)
        bridged_submission = bridged_submission[0]
    except IndexError:
        _log.info(
            "Unable to find a bridged submission for comment on MR %d, commit %s, forge %r",
            merge_id,
            commit,
            git_forge,
        )
        return

    from_email = settings.PATCHLAB_FROM_EMAIL.format(forge_user=["author"])
    # From the bridged_submission, find the in-reply-to, create email.
    headers = {
        "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
        "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
        "In-Reply-To": bridged_submission.submission.msgid,
        "X-Patchlab-Comment": comment["url"],
    }
    subject = "Re: " + " ".join(
        message_from_string(bridged_submission.submission.headers)[
            "Subject"
        ].splitlines()
    )
    wrapped_description = "\n".join(
        [
            textwrap.fill(line, width=72, replace_whitespace=False)
            for line in comment["note"].splitlines()
        ]
    )
    body = (
        f"From: {author['name']} on {git_forge.host}\n{comment['url']}\n\n{wrapped_description}\n"
        f""
    )
    comment = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[git_forge.project.listemail],
        headers=headers,
        reply_to=[git_forge.project.listemail],
    )
    with get_connection(fail_silently=False) as conn:
        patchwork_parser.parse_mail(comment.message(), list_id=git_forge.project.listid)
        comment.connection = conn
        comment.send(fail_silently=False)


def _record_bridging(listid: str, merge_id: int, email: EmailMessage) -> None:
    """
    Create the Patchwork submission records. This would happen when the mail
    hit the mailing list, but doing so now lets us associate them with a
    BridgedSubmission so we can post follow-up comments.

    Raises:
        ValueError: If the emails cannot be parsed by patchwork or is a duplicate.
        Submission.DoesNotExist: If the Submission object isn't created by
            patchwork; this indicates Patchwork has changed in some way or
            there's a bug in this function.
    """
    try:
        patchwork_parser.parse_mail(email.message(), list_id=listid)
    except patchwork_parser.DuplicateMailError:
        _log.error(
            "Message ID %s is already in the database; do not call "
            "_record_bridging twice with the same email",
            email.extra_headers["Message-ID"],
        )
        raise ValueError(email)

    try:
        submission = Submission.objects.get(msgid=email.extra_headers["Message-ID"])
    except Submission.DoesNotExist:
        _log.error(
            "Patchwork did not save the email which likely means the subject "
            "match field on the project with listid '%s' is filtering out "
            "emails with subjects like '%s'",
            listid,
            email.subject,
        )
        raise

    bridged_submission = BridgedSubmission(
        submission=submission,
        git_forge=submission.project.git_forge,
        merge_request=merge_id,
        commit=email.extra_headers.get("X-Patchlab-Commit"),
        series_version=email.extra_headers.get("X-Patchlab-Series-Version", 1),
    )
    bridged_submission.save()
    return bridged_submission
