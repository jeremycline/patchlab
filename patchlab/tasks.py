# SPDX-License-Identifier: GPL-2.0-or-later
from email import message_from_string, utils as email_utils
from typing import List
import logging
import re
import urllib

from celery import shared_task
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
  $ git config remote.gitlab.fetch '+refs/merge-requests/*:refs/remotes/origin/merge-requests/*'
  $ git fetch gitlab

Finally, check out the merge request:

  $ git checkout merge-requests/{merge_id}

It is also possible to review the merge request on GitLab at:
    {merge_url}
"""


def _prepare_emails(gitlab, git_forge, project, merge_request):
    """Prepare a set of emails that represent the given merge request."""
    mr_author = gitlab.users.get(merge_request.author["id"])
    mr_from = f"{mr_author.name} <{mr_author.email}>"
    commits = list(reversed(list(merge_request.commits())))
    num_commits = len(commits)

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

    emails = []
    if num_commits > 1:
        # Compose a cover letter based on the pull request description.
        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
        }
        cover_letter = EmailMessage(
            subject=f"[{branch.subject_prefix} PATCH 0/{num_commits}] {merge_request.title}",
            body=merge_request.description,
            to=[git_forge.project.listemail],
            cc=[mr_from],
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )

        if num_commits > settings.PATCHLAB_MAX_EMAILS:
            cover_letter.body = BIG_EMAIL_TEMPLATE.format(
                description=merge_request.description,
                remote_url=f"{project.web_url}.git",
                merge_id=merge_request.id,
                merge_url=merge_request.web_url,
            )
            return [cover_letter]

        emails.append(cover_letter)

    for i, commit in enumerate(commits, 1):
        # This currently only works for public projects; authenticating with a
        # token does not work.
        # https://gitlab.com/gitlab-org/gitlab/issues/26228
        response = gitlab.session.get(f"{project.web_url}/commit/{commit.id}.patch")
        response.raise_for_status()
        patch = message_from_string(response.text)

        match = PREFIX_RE.match(patch["Subject"])
        if match:
            old_subject = patch["Subject"][match.span()[1] :]
        else:
            old_subject = " " + patch["Subject"].strip()
        patch_prefix = f"[{branch.subject_prefix} PATCH"
        if num_commits > 1:
            patch_prefix += f" {str(i)}/{num_commits}"
        patch_prefix += "]"
        subject = patch_prefix + old_subject
        patch_author = patch["From"]

        headers = {
            "Date": email_utils.formatdate(localtime=settings.EMAIL_USE_LOCALTIME),
            "Message-ID": email_utils.make_msgid(domain=DNS_NAME),
            "X-Patchlab-Patch-Author": patch_author,
            "X-Patchlab-Merge-Request": f"{merge_request.web_url}",
            "X-Patchlab-Commit": f"{commit.id}",
        }

        email = EmailMessage(
            subject=subject,
            body=patch.get_payload(),
            to=[git_forge.project.listemail],
            cc=[mr_from],
            headers=headers,
            reply_to=[git_forge.project.listemail],
        )
        emails.append(email)

    return emails


def _record_bridging(listid: str, merge_id: int, emails: List[EmailMessage]) -> None:
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
    for email in emails:
        try:
            patchwork_parser.parse_mail(email.message(), list_id=listid)
        except patchwork_parser.DuplicateMailError:
            _log.error(
                "Message ID %s is already in the database; do not call "
                "_record_bridging twice with the same email",
                email.extra_headers["Message-ID"],
            )
            raise ValueError(emails)

    for email in emails:
        submission = Submission.objects.get(msgid=email.extra_headers["Message-ID"])
        bridged_submission = BridgedSubmission(
            submission=submission,
            merge_request=merge_id,
            commit=email.extra_headers.get("X-Patchlab-Commit"),
        )
        bridged_submission.save()


def _email_merge_request(host: str, project_id: int, merge_id: int) -> None:
    """
    Email a merge request to a mailing list.
    """
    gitlab = gitlab_module.Gitlab.from_config(host)
    project = gitlab.projects.get(project_id)
    merge_request = project.mergerequests.get(merge_id)

    try:
        git_forge = GitForge.objects.get(
            host=host,
            project_id=project_id,
            development_branch=merge_request.target_branch,
        )
    except GitForge.DoesNotExist:
        _log.error(
            "Web hook received for project id %d on %s, but no git forge exists",
            project_id,
            host,
        )
        return

    # TODO backoff on failure, gitlab might be down
    emails = _prepare_emails(gitlab, git_forge, project, merge_request)
    # TODO backoff, database might be down
    _record_bridging(git_forge.project.listid, merge_id, emails)
    # TODO catch errors, email server might be down
    with get_connection(fail_silently=False) as conn:
        for email in emails:
            email.connection = conn
            email.send(fail_silently=False)


@shared_task
def merge_request_hook(webhook_payload: dict) -> None:
    """
    Handle incoming merge request web hooks.

    If a merge request is made up of more than a single commit, a cover letter
    is created using the merge request description.

    Args:
        merge_request: The merge request web hook payload from GitLab
    """
    project_id = webhook_payload["project"]["id"]
    merge_id = webhook_payload["object_attributes"]["id"]
    merge_url = webhook_payload["object_attributes"]["url"]
    host = urllib.parse.urlsplit(merge_url).hostname

    _email_merge_request(host, project_id, merge_id)


@shared_task
def email_comment(comment):
    pass
