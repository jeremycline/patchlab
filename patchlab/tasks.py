from email.policy import EmailPolicy
from email.message import EmailMessage
from tempfile import TemporaryDirectory
import os
import subprocess

from celery import shared_task
import gitlab as gitlab_module

subject_prefix = "ARK INTERNAL PATCH"
project_list = "some_list@example.com"
project_url = "https://localhost:8443"

# The policy used when parsing patches as emails.
#
# Refer to https://docs.python.org/3/library/email.policy.html for details on
# individual policy options.
email_policy = EmailPolicy()


@shared_task
def email_merge_request(project_id: int, merge_id: int) -> None:
    """
    Celery task to email a merge request.

    If a merge request is made up of more than a single commit, a cover letter
    is created using the merge request description.

    Args:
        merge_request: The web hook payload from GitLab
    """
    gitlab = gitlab_module.Gitlab.from_config("test")
    project = gitlab.projects.get(project_id)
    merge_request = project.mergerequests.get(merge_id)
    mr_author = gitlab.users.get(merge_request.author["id"])
    mr_from = f"{mr_author.name} <{mr_author.email}>"

    # Don't spam people with merge requests that can't be merged.
    if merge_request.merge_status != "can_be_merged":
        return

    commits = list(merge_request.commits())

    cover_letter = None
    if len(commits) > 1:
        # Compose a cover letter based on the pull request description.
        # TODO People may want a series summary (commits by author, etc)
        cover_letter = EmailMessage(policy=email_policy)
        cover_letter[
            "Subject"
        ] = f"[{subject_prefix} 0/{len(commits)}] {merge_request.title}"
        cover_letter["From"] = mr_from
        cover_letter.set_content(merge_request.description)

    patches = []
    for commit in commits:
        # TODO collect repo root from project model
        #
        # This currently only works for public projects; authenticating with a
        # token does not work.
        # https://gitlab.com/gitlab-org/gitlab/issues/26228
        response = gitlab.session.get(
            f"{project_url}/root/kernel/commit/{commit.id}.patch"
        )
        response.raise_for_status()
        patches.append(response.text)

    with TemporaryDirectory() as dirname:
        if cover_letter:
            with open(os.path.join(dirname, "0000-cover-letter.patch"), "w") as fd:
                fd.write(cover_letter.as_string())

        for i, patch in enumerate(patches, 1):
            with open(os.path.join(dirname, f"{str(i).zfill(4)}-.patch"), "w") as fd:
                fd.write(patch)

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
        result = subprocess.run(
            [
                "git",
                "-C",
                dirname,
                "send-email",
                f"--to={project_list}",
                f'--subject-prefix="{subject_prefix}"',
                dirname,
            ],
            capture_output=True,
        )
        print(result)


@shared_task
def email_comment(comment):
    pass
