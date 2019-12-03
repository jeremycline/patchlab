# SPDX-License-Identifier: GPL-2.0-or-later
"""
This module deals with turning Gitlab objects (merge requests, comments) into
emails.
"""
from email import message_from_string, utils as email_utils
import logging
import re
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

Reviewing locally, set up your repository to fetch from the GitLab remote:

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

    commits = list(reversed(list(merge_request.commits())))
    num_commits = len(commits)

    emails = []
    if num_commits > 1:
        # Compose a cover letter based on the pull request description.
        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
        }
        body = (
            f"From: {merge_request.author['username']} on {git_forge.host}\n\n"
            f"{merge_request.description}"
        )
        sanitized_subject = " ".join(merge_request.title.splitlines())
        cover_letter = EmailMessage(
            subject=f"[{branch.subject_prefix} PATCH 0/{num_commits}] {sanitized_subject}",
            body=body,
            to=[git_forge.project.listemail],
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )

        if num_commits > settings.PATCHLAB_MAX_EMAILS:
            cover_letter.body = BIG_EMAIL_TEMPLATE.format(
                description=body,
                remote_url=f"{project.web_url}.git",
                merge_id=merge_request.id,
                merge_url=merge_request.web_url,
            )
            return [cover_letter]

        emails.append(cover_letter)

    in_reply_to = emails[0].extra_headers["Message-ID"] if emails else None
    for i, commit in enumerate(commits, 1):
        # This currently only works for public projects; authenticating with a
        # token does not work.
        # https://gitlab.com/gitlab-org/gitlab/issues/26228
        response = gitlab.session.get(f"{project.web_url}/commit/{commit.id}.patch")
        response.raise_for_status()
        patch = message_from_string(response.text)

        patch_num = "" if len(commits) == 1 else f" {str(i)}/{num_commits}"
        sanitized_patch_title = " ".join(commit.title.splitlines())
        subject = f"[{branch.subject_prefix} PATCH{patch_num}] {sanitized_patch_title}"
        patch_author = patch["From"]

        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Patch-Author": patch_author,
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
            "X-Patchlab-Commit": f"{commit.id}",
        }
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to

        email = EmailMessage(
            subject=subject,
            body=f"From: {patch_author}\n\n{patch.get_payload()}",
            to=[git_forge.project.listemail],
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )
        emails.append(email)

    return emails


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

    submission = Submission.objects.get(msgid=email.extra_headers["Message-ID"])
    bridged_submission = BridgedSubmission(
        submission=submission,
        merge_request=merge_id,
        commit=email.extra_headers.get("X-Patchlab-Commit"),
    )
    bridged_submission.save()
    return bridged_submission
