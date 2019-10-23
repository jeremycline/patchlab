from email import policy, message_from_string, utils as email_utils
from email.message import EmailMessage
from tempfile import TemporaryDirectory
from typing import List
import logging
import os
import secrets
import string
import subprocess
import urllib

from celery import shared_task
from django.conf import settings
from gitlab.v4.objects import MergeRequest, Project
from patchwork import parser as patchwork_parser
from patchwork.models import Submission
import gitlab as gitlab_module

from patchlab.models import GitForge, BridgedSubmission

_log = logging.getLogger(__name__)

#: The policy used when parsing patches as emails.
#:
#: Refer to https://docs.python.org/3/library/email.policy.html for details on
#: individual policy options.
email_policy = policy.EmailPolicy()

BASE36 = string.ascii_lowercase + string.digits

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


def _prepare_emails(
    gitlab: gitlab_module.Gitlab,
    project: Project,
    merge_request: MergeRequest,
    subj_prefix: str,
) -> List[EmailMessage]:
    """Prepare a set of emails that represent the given merge request."""

    mr_author = gitlab.users.get(merge_request.author["id"])
    mr_from = f"{mr_author.name} <{mr_author.email}>"
    commits = list(reversed(list(merge_request.commits())))
    num_commits = len(commits)

    emails = []
    if num_commits > 1:
        # Compose a cover letter based on the pull request description.
        cover_letter = EmailMessage(policy=email_policy)
        cover_letter["From"] = mr_from
        cover_letter["Date"] = email_utils.formatdate()
        cover_letter[
            "Subject"
        ] = f"[{subj_prefix} 0/{num_commits}] {merge_request.title}"
        cover_letter["Message-ID"] = email_utils.make_msgid(
            idstring="".join([secrets.choice(BASE36) for _ in range(4)])
        )
        cover_letter["X-Patchlab-Merge-Request"] = f"{merge_request.web_url}"
        cover_letter.set_content(merge_request.description)
        emails.append(cover_letter)

    if num_commits > settings.PATCHLAB_MAX_EMAILS:
        # The pull request is too big to email; just use the cover letter
        body = BIG_EMAIL_TEMPLATE.format(
            description=merge_request.description,
            remote_url=f"{project.web_url}.git",
            merge_id=merge_request.id,
            merge_url=merge_request.web_url,
        )
        cover_letter.set_content(body)
        return [cover_letter]

    for i, commit in enumerate(commits, 1):
        # This currently only works for public projects; authenticating with a
        # token does not work.
        # https://gitlab.com/gitlab-org/gitlab/issues/26228
        response = gitlab.session.get(f"{project.web_url}/commit/{commit.id}.patch")
        response.raise_for_status()
        patch = message_from_string(response.text)

        patch_prefix = f"[{subj_prefix}"
        if num_commits > 1:
            patch_prefix += f" {str(i)}/{num_commits}]"
        else:
            patch_prefix += "]"
        old_subj = patch["Subject"][7:].strip()
        del patch["Subject"]
        patch["Subject"] = f"{patch_prefix} {old_subj}"
        patch["Message-ID"] = email_utils.make_msgid(
            idstring="".join([secrets.choice(BASE36) for _ in range(4)])
        )
        patch["X-Patchlab-Merge-Request"] = f"{merge_request.web_url}"
        patch["X-Patchlab-Commit"] = f"{commit.id}"
        emails.append(patch)

    return emails


def _record_bridging(
    forge: GitForge, merge_id: int, emails: List[EmailMessage]
) -> None:
    """
    Create the Patchwork submission records. This would happen when the mail
    hit the mailing list, but doing so now lets us associate them with a
    BridgedSubmission so we can post follow-up comments.

    Raises:
        ValueError: If the email can't be parsed by Patchwork. This is a fatal error in
            how we're creating the patches.
        patchwork_parser.DuplicateMailError: If the mail already exists in patchwork;
            this indicates we somehow managed to create a colliding Message-ID and we
            should retry this whole task.
        Submission.DoesNotExist: A submission was not correctly added to the database
            by Patchwork. This is a bug.
    """
    for email in emails:
        patchwork_parser.parse_mail(email, list_id=forge.project.listid)

    for email in emails:
        submission = Submission.objects.get(msgid=email["Message-ID"])
        bridged_submission = BridgedSubmission(
            submission=submission,
            merge_request=merge_id,
            commit=email.get("X-Patchlab-Commit"),
        )
        bridged_submission.save()


def _send_patches(to_email: str, emails: list) -> None:
    """
    Send a set of emails to the given email list.

    This uses git send-email in order to take advantage of its parsing of
    Cc tags and such.
    """
    with TemporaryDirectory() as dirname:
        for i, email in enumerate(emails, 0):
            with open(os.path.join(dirname, f"{str(i).zfill(4)}.patch"), "w") as fd:
                fd.write(email.as_string())

        # Weird hack - git send-email won't do it outside a git repo with at least one commit.
        subprocess.run(["git", "init", dirname], check=True)
        subprocess.run(["git", "-C", dirname, "add", "-A"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                dirname,
                "commit",
                '--author="Nobody <nobody@example.com>"',
                "-m",
                "Nothing",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", dirname, "send-email", f"--to={to_email}", dirname],
            check=True,
        )


@shared_task
def email_merge_request(webhook_payload: dict) -> None:
    """
    Celery task to email a merge request.

    If a merge request is made up of more than a single commit, a cover letter
    is created using the merge request description.

    Args:
        merge_request: The web hook payload from GitLab
    """
    project_id = webhook_payload["project"]["id"]
    merge_id = webhook_payload["object_attributes"]["id"]
    merge_url = webhook_payload["object_attributes"]["url"]
    host = urllib.parse.urlsplit(merge_url).hostname

    try:
        git_forge = GitForge.objects.get(host=host, project_id=project_id)
    except GitForge.DoesNotExist:
        _log.error(
            "Web hook received for project id %d on %s, but no git forge exists",
            project_id,
            host,
        )
        return

    # TODO document that the python-gitlab settings need a section per hostname
    gitlab = gitlab_module.Gitlab.from_config()
    project = gitlab.projects.get(project_id)
    merge_request = project.mergerequests.get(merge_id)

    # Don't spam people with merge requests that can't be merged.
    if merge_request.merge_status != "can_be_merged":
        return

    emails = _prepare_emails(gitlab, project, merge_request, git_forge.subject_prefix)
    try:
        _record_bridging(git_forge, merge_id, emails)
    except patchwork_parser.DuplicateMailError:
        _log.error(
            "Message ID collides with an existing email in Patchwork; this is a bug."
            " Recovering by restarting task"
        )
        raise
    except Submission.DoesNotExist:
        _log.error(
            "Message-ID should have been in the database, but wasn't; this is a bug"
        )
        raise
    except ValueError:
        _log.exception("The following email could not be parsed by Patchwork: %s")
        raise

    _send_patches(git_forge.project.listemail, emails)


@shared_task
def email_comment(comment):
    pass
