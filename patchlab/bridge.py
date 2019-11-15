# SPDX-License-Identifier: GPL-2.0-or-later
"""
Bridge Patchwork to GitLab.

The bridge makes use of the Patchwork `events
<https://patchwork.readthedocs.io/en/latest/api/rest/schemas/v1.1/#get--api-1.1-events->`_
API to retrieve completed patch series, applies them to a git repository with
git-am, pushes them to a GitLab repository, and opens a pull request.
"""

from typing import Optional, Sequence
import logging
import subprocess

from django.core.mail import EmailMessage
from patchwork.models import Project, Series
from patchwork.views.utils import series_to_mbox
import backoff
import gitlab as gitlab_module
import requests

from .models import BridgedSubmission, GitForge


_log = logging.Logger(__name__)

session = requests.Session()
gitlab = None


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


def poll_events(api_url: str, project: str, since: Optional[str]) -> Sequence[dict]:
    """
    Poll events from a project since a certain datetime.
    """
    params = {"category": "series-completed", "project": project}
    if since:
        params["since"] = since

    response = session.get(f"{api_url}/events/", params=params, timeout=30)
    response.raise_for_status()
    for event in response.json():
        yield event

    next_page = _link(response)
    while next_page:
        response = session.get(next_page, timeout=30)
        response.raise_for_status()
        for event in response.json():
            yield event


def _link(response: requests.Response, ref: str = "next") -> Optional[str]:
    """
    Parse the page URL from the Link header given a ref.

    Arguments:
        response: The response object that might contain a pagination link.
        ref: The URL type to retrieve. For possible values, refer to
            https://patchwork.readthedocs.io/en/latest/api/rest/#link-header
    """
    try:
        next_page = [
            l["url"]
            for l in requests.utils.parse_header_links(response.headers["Link"])
            if l["ref"] == ref
        ]
    except KeyError:
        return

    try:
        return next_page[0]
    except IndexError:
        return


class Retry(Exception):
    """Raised in a helper method if a step needs retrying due to missing resources"""

    pass


@backoff.on_exception(
    backoff.expo,
    (
        gitlab_module.exceptions.GitlabConnectionError,
        requests.exceptions.ConnectionError,
        Retry,
    ),
    logger=__name__,
)
def open_merge_request(
    gitlab: gitlab_module.Gitlab, patchwork_project: Project, series_id: int
) -> None:
    """
    Convert a Patchwork series into a pull request in GitLab.

    The series is converted by:

    1. Checking out the latest version of the configured development branch
       from GitLab.
    2. Checking out a new branch for the series using "email/series-<id>" as
       the branch naming scheme.
    3. Using "git-am" to apply the series to the new branch.
    4. Opening a merge request using git push options with GitLab.

    Pull requests opened with the function are tagged with ``From email``.

    Args:
        series: A dictionary representing a series as retrieved from
            the patchwork API.

    Raises:
        django.db.OperationalError: If the database connection is unavailable.
            The connection should be restarted before retrying this function.
        gitlab_module.exceptions.GitlabError: If a GitLab API call fails in an unrecoverable
            or un-handled manner.
        subprocess.TimeoutExpired: If a subprocess call exceeds its timeout.
        subprocess.CalledProcessError: If a subprocess call fails in an unrecoverable manner.
    """
    branch_name = f"emails/series-{series_id}"
    try:
        gitlab_project = gitlab.projects.get(patchwork_project.git_forge.forge_id)
    except gitlab_module.exceptions.GitlabGetError as e:
        if e.response_code >= 500:
            raise Retry(str(e))
        else:
            _log.error("Fatal error requesting %r: %r", patchwork_project.git_forge, e)
            raise

    if gitlab_project.mergerequests.list(source_branch=branch_name, state="all"):
        _log.info(
            "A merge request for branch %s already exists, skipping series", branch_name
        )
        return

    series = Series.objects.get(pk=series_id)
    if series.cover_letter:
        description = series.cover_letter.content
        target_branch = patchwork_project.git_forge.branch(series.cover_letter)
    else:
        patch = series.patches.order_by("number").first()
        description = patch.content
        target_branch = patchwork_project.git_forge.branch(patch)

    _reset_tree(patchwork_project.git_forge, target_branch)

    try:
        _create_branch(patchwork_project.git_forge, series, branch_name)
    except ValueError:
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
            submission=series.cover_letter.submission_ptr,
            merge_request=merge_request.id,
        ).save()

    for patch, commit in zip(
        series.patches.order_by("number").all(), merge_request.commits()
    ):
        bridged_submission = BridgedSubmission(
            submission=patch.submission_ptr,
            merge_request=merge_request.id,
            commit=commit.id,
        )
        bridged_submission.save()


def _reset_tree(git_forge, target_branch):
    """Reset a git tree to the latest upstream commit on the development branch."""
    subprocess.run(
        ["git", "-C", git_forge.repo_path, "fetch", "origin"], timeout=300, check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            git_forge.repo_path,
            "reset",
            "--hard",
            f"origin/{target_branch}",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", git_forge.repo_path, "am", "--abort"], check=False,
    )
    subprocess.run(
        ["git", "-C", git_forge.repo_path, "checkout", f"origin/{target_branch}"],
        check=True,
    )


@backoff.on_exception(
    backoff.expo,
    (subprocess.CalledProcessError, subprocess.TimeoutExpired),
    logger=__name__,
)
def _create_branch(git_forge, series, branch_name):
    """Create a branch on the remote from a series."""
    subprocess.run(
        ["git", "-C", git_forge.repo_path, "branch", "-D", branch_name], check=False
    )
    subprocess.run(
        ["git", "-C", git_forge.repo_path, "checkout", "-b", branch_name], check=True
    )
    try:
        subprocess.run(
            ["git", "-C", git_forge.repo_path, "am"],
            input=series_to_mbox(series),
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        _notify_am_failure(git_forge, series)
        raise ValueError("Series cannot be applied")

    subprocess.run(
        ["git", "-C", git_forge.repo_path, "push", "-f", "origin", branch_name],
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
