# SPDX-License-Identifier: GPL-2.0-or-later
"""
Bridge Patchwork to GitLab.

The bridge makes use of the Patchwork `events
<https://patchwork.readthedocs.io/en/latest/api/rest/schemas/v1.1/#get--api-1.1-events->`_
API to retrieve completed patch series, applies them to a git repository with
git-am, pushes them to a GitLab repository, and opens a pull request.
"""

import email
import logging
import os
import subprocess

from celery import exceptions as celery_exceptions
from django.core.mail import EmailMessage
from patchwork.models import Comment, Project, Series
from patchwork.views.utils import series_to_mbox
import backoff
import gitlab as gitlab_module
import requests

from .models import BridgedSubmission, GitForge


_log = logging.Logger(__name__)

GIT_AM_FAILURE = """
Hello,

We were unable to apply this patch series to the current development branch.
The current head of the {branch_name} branch is commit {commit}.

Please rebase this series against the current development branch and resend it
or, if you prefer never seeing this email again, submit your series as a pull
request:

  1. Create an account and fork {url}.
  2. git remote add <remote-name> <your-forked-repo>
  3. git push <remote-name> <branch-name> --push-option=merge_request.create \\
       --push-option=merge_request.title="{title}"
"""


def submit_gitlab_comment(gitlab: gitlab_module.Gitlab, comment: Comment) -> None:
    """Bridge Patchwork comments to Gitlab."""
    try:
        bridged_submission = BridgedSubmission.objects.get(
            submission=comment.submission
        )
    except BridgedSubmission.DoesNotExist:
        _log.info("Unable to find a bridged submission for %s", str(comment.submission))
        return

    project = gitlab.projects.get(comment.submission.project.git_forge.forge_id)
    merge_request = project.mergerequests.get(bridged_submission.merge_request)

    # Turn Ack-by/Nack-by into Gitlab tags. This doesn't attempt to undo any
    # previous tags so if someone Acks and then Nacks the merge request will
    # have both tags.
    for match in comment.response_re.finditer(comment.content):
        tag, name_and_address = match.group(0).split(":")
        _, address = email.utils.parseaddr(name_and_address)
        merge_request.labels.append(f"{tag}: {address}")
    merge_request.save()

    note = merge_request.notes.create(
        {
            "body": f"{comment.submitter} commented via email:\n```\n{comment.content}\n```"
        }
    )

    return merge_request, note


@backoff.on_exception(
    backoff.expo,
    (
        gitlab_module.exceptions.GitlabConnectionError,
        requests.exceptions.ConnectionError,
    ),
    logger=__name__,
)
def open_merge_request(
    gitlab: gitlab_module.Gitlab, series: Series, working_dir: str
) -> None:
    """
    Convert a Patchwork series into a pull request in GitLab.

    The series is converted by:

    1. Checking out a git worktree based on the clone from the Git Forge.
    2. Checking out a new branch for the series using "email/series-<id>" as
       the branch naming scheme.
    3. Using "git-am" to apply the series to the new branch.
    4. Pushing the git branch to the remote.
    5. Opening a merge request via the API

    Pull requests opened with the function are tagged with ``From email``.

    Raises:
        django.db.OperationalError: If the database connection is unavailable.
            The connection should be restarted before retrying this function.
        gitlab_module.exceptions.GitlabError: If a GitLab API call fails in an unrecoverable
            or un-handled manner.
        subprocess.TimeoutExpired: If a subprocess call exceeds its timeout.
        subprocess.CalledProcessError: If a subprocess call fails in an unrecoverable manner.
    """
    patchwork_project = series.project
    branch_name = f"emails/series-{series.id}"
    try:
        gitlab_project = gitlab.projects.get(patchwork_project.git_forge.forge_id)
    except gitlab_module.exceptions.GitlabGetError as e:
        if e.response_code >= 500:
            raise celery_exceptions.Retry(message=str(e), exc=e)
        else:
            _log.error("Fatal error requesting %r: %r", patchwork_project.git_forge, e)
            raise

    if gitlab_project.mergerequests.list(source_branch=branch_name, state="all"):
        _log.info(
            "A merge request for branch %s already exists, skipping series", branch_name
        )
        return

    try:
        if series.cover_letter:
            description = series.cover_letter.content
            target_branch = patchwork_project.git_forge.branch(series.cover_letter)
        else:
            patch = series.patches.order_by("number").first()
            description = patch.content
            target_branch = patchwork_project.git_forge.branch(patch)
    except ValueError as e:
        # Raised if there's no branch for the given patch tags.
        _log.error(str(e))
        return

    try:
        _create_remote_branch(
            patchwork_project, series, branch_name, target_branch, working_dir
        )
    except ValueError:
        _notify_am_failure(patchwork_project.git_forge, series)
        return

    merge_request = gitlab_project.mergerequests.create(
        {
            "source_branch": branch_name,
            "target_branch": target_branch,
            "title": series.name,
            "labels": ["From email"],
            "remove_source_branch": True,
            "allow_collaboration": True,
            "description": f"```\n{description}\n```",  # Email formatting + Markdown looks bad
        }
    )

    if series.cover_letter:
        BridgedSubmission(
            git_forge=patchwork_project.git_forge,
            submission=series.cover_letter.submission_ptr,
            merge_request=merge_request.iid,
        ).save()

    for patch, commit in zip(
        series.patches.order_by("number").all(), merge_request.commits()
    ):
        bridged_submission = BridgedSubmission(
            git_forge=patchwork_project.git_forge,
            submission=patch.submission_ptr,
            merge_request=merge_request.iid,
            commit=commit.id,
        )
        bridged_submission.save()


def _create_remote_branch(
    patchwork_project: Project,
    series: Series,
    branch_name: str,
    target_branch: str,
    working_dir: str,
) -> None:
    """
    Create a branch on the remote for the given series.

    Raises:
        ValueError: If the series cannot be applied to the target branch.
    """
    worktree_path = os.path.join(
        working_dir,
        f"{patchwork_project.git_forge.host}-{patchwork_project.git_forge.forge_id}",
    )
    if not os.path.exists(worktree_path):
        subprocess.run(
            [
                "git",
                "-C",
                patchwork_project.git_forge.repo_path,
                "worktree",
                "add",
                "-f",
                "-B",
                branch_name,
                worktree_path,
                f"origin/{target_branch}",
            ],
            timeout=300,
            check=True,
        )

    subprocess.run(
        ["git", "-C", worktree_path, "fetch", "origin"], timeout=300, check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            worktree_path,
            "checkout",
            "-f",
            "-B",
            branch_name,
            f"origin/{target_branch}",
        ],
        check=True,
    )

    try:
        subprocess.run(
            ["git", "-C", worktree_path, "am"],
            input=series_to_mbox(series),
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        subprocess.run(["git", "-C", worktree_path, "am", "--abort"], check=True)
        raise ValueError(f"Unable to apply series: {str(e)}")

    subprocess.run(
        ["git", "-C", worktree_path, "push", "-f", "origin", branch_name],
        check=True,
        timeout=60,
    )


def _notify_am_failure(git_forge: GitForge, series: Series) -> None:
    """Notify a developer that the series could not be applied to a project."""
    target_branch = git_forge.branch(series.patches.first())
    commit = subprocess.run(
        ["git", "-C", git_forge.repo_path, "rev-parse", f"origin/{target_branch}"],
        check=True,
        capture_output=True,
        text=True,
    )

    if series.cover_letter:
        msgid = series.cover_letter.msgid
    else:
        msgid = series.patches.first().msgid

    body = GIT_AM_FAILURE.format(
        branch_name=target_branch,
        commit=commit.stdout,
        url=git_forge.project.web_url,
        title=series.name,
    )
    mail = EmailMessage(
        subject=f"Re: {series.name}",
        body=body,
        headers={"In-Reply-To": f"{msgid}"},
        to=[series.submitter.email],
    )
    mail.send()
