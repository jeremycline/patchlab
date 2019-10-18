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
import time

import gitlab as gitlab_module
import requests


_log = logging.Logger(__name__)

# TODO: Make settings
PATCHWORK_URL = "http://localhost:8000/api/1.1"
GITLAB_PROJECT_ID = 1
PROJECT = "ark"

session = requests.Session()
gitlab = None


# TODO configify repos
forge = {
    "patchwork_project": "ark",
    "repo_path": "/var/lib/patchlab/ark",
    "development_branch": "internal",
    "pull_remote": "origin",
    "push_remote": "origin",
}


def poll_events(project: str, since: Optional[str]) -> Sequence[dict]:
    """
    Poll events from a project since a certain datetime.
    """
    params = {"category": "series-completed", "project": project}
    if since:
        params["since"] = since

    response = session.get(f"{PATCHWORK_URL}/events/", params=params, timeout=30)
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


def open_merge_request(title: str, branch_name: str, mbox: str) -> None:
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
        requests.RequestException: If the patch series cannot be retrieved
            from Patchwork.
    """
    # TODO: Fails if the repo path doesn't exist, the remote doesn't exist, the
    # branch doesn't exist, git isn't installed. All need to halt operation
    # and presented to the user.
    try:
        subprocess.run(
            [
                "git",
                "-C",
                forge["repo_path"],
                "reset",
                "--hard",
                f"{forge['pull_remote']/forge['development_branch']}",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", forge["repo_path"], "checkout", forge["development_branch"]],
            check=True,
        )
    except subprocess.CalledProcessError:
        # TODO Failure here indicates a configuration error. Don't retry.
        raise

    # TODO: This could fail if the network is borked. We want to retry if this fails.
    try:
        subprocess.run(
            ["git", "-C", forge["repo_path"], "pull"], timeout=60, check=True
        )
    except subprocess.TimeoutExpired:
        raise
    except subprocess.CalledProcessError:
        raise

    try:
        subprocess.run(
            ["git", "-C", forge["repo_path"], "branch", "-D", branch_name], check=False
        )
        subprocess.run(
            ["git", "-C", forge["repo_path"], "checkout", "-b", branch_name], check=True
        )
    except subprocess.CalledProcessError:
        # TODO when can checkout fail?
        raise

    try:
        subprocess.run(
            ["git", "-C", forge["repo_path"], "am"], input=mbox, text=True, check=True
        )
    except subprocess.CalledProcessError:
        # TODO git-am exited non-zero, complain to the developer with actionable info.
        raise

    try:
        subprocess.run(
            [
                "git",
                "-C",
                forge["repo_path"],
                "push",
                "--push-option=merge_request.create",
                "--push-option=merge_request.remove_source_branch",
                f'--push-option=merge_request.title="{title}"',
                '--push-option=merge_request.label="From email"',
                "-f",
                forge["push_remote"],
                branch_name,
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        # TODO This could fail because the network is borked or we don't have write
        # access to the remote.
        raise


def pr_exists(project_id: int, branch_name: str) -> bool:
    project = gitlab.projects.get(project_id)
    try:
        project.branches.get(branch_name)
        _log.info("The %s branch already exists, skipping series")
        return True
    except gitlab_module.exceptions.GitlabGetError as e:
        if e.response_code != 404:
            _log.error("Probing the GitLab project for %s failed (%r)", branch_name, e)
        return False


if __name__ == "__main__":
    gitlab = gitlab_module.Gitlab.from_config()

    try:
        with open("last_event", "r") as f:
            since = f.read()
    except IOError:
        since = None

    while True:
        for event in poll_events(forge["patchwork_project"], since):
            branch_name = f'emails/series-{event["payload"]["series"]["id"]}'
            mbox = session.get(event["payload"]["series"]["mbox"], timeout=30)
            if not pr_exists(GITLAB_PROJECT_ID, branch_name):
                open_merge_request(
                    event["payload"]["series"]["name"], branch_name, mbox.text
                )

            with open("last_event", "w") as f:
                f.write(event["date"])
        time.sleep(60)
