# SPDX-License-Identifier: GPL-2.0-or-later
import email
import os
import re

from django.conf import settings
from django.db import models

from patchwork.models import Project, Submission, validate_regex_compiles


class BridgedSubmission(models.Model):
    """
    Information about Patchwork submissions we've bridged back and forth.

    This is necessary so that comments converted to email are properly threaded.

    Attributes:
        submission: A one-to-one relationship with a
            :class:`patchwork.models.Submission`.
        merge_request: The merge request ID in the Git forge.
        commit: The commit hash of the bridged submission, if the submission in
            question is a patch. May be null for comments.
    """

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, primary_key=True
    )
    merge_request = models.IntegerField(null=False, blank=False)
    commit = models.CharField(max_length=128, null=True, blank=True)
    series_version = models.IntegerField(null=True, blank=True)
    git_forge = models.ForeignKey("GitForge", on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=["merge_request", "git_forge"]),
        ]


class GitForge(models.Model):
    """
    Represents a Git forge being bridged to and from email.

    Attributes:
        project: A one-to-one relationship with a
            :class:`patchwork.models.Project`.
        host: The hostname of the Git forge; this is used for a uniqueness
            constraint on it combined with the forge ID and development branch.
        forge_id: The unique ID of the project in the Git forge. For Gitlab,
            this is prominently displayed on the project home page.
        subject_prefix: The subject prefix to prepend to patches being sent
            to the list when a pull request is opened against the branch.
        development_branch: The branch in the Git forge used for development;
            this is the branch pull requests are opened against.
    """

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="git_forge"
    )
    host = models.CharField(
        max_length=255,
        help_text="The hostname of the Git forge; this is used "
        "to find the correct configuration section in the python-gitlab.cfg file.",
    )
    forge_id = models.IntegerField(
        help_text="The unique ID of the project in the Git forge. For Gitlab, "
        "this is prominently displayed on the project home page."
    )

    class Meta:
        unique_together = [["host", "forge_id"]]
        indexes = [models.Index(fields=["host", "forge_id"])]

    def __str__(self):
        return (
            f"{self.project.name} hosted on {self.host} as project "
            f" ID {self.project_id}"
        )

    def __repr__(self):
        return (
            f"GitForge(host={self.host}, forge_id={self.forge_id}, "
            f"project={repr(self.project)})"
        )

    @property
    def repo_path(self):
        return os.path.join(settings.PATCHLAB_REPO_DIR, f"{self.host}-{self.forge_id}")

    def branch(self, submission: Submission) -> str:
        """
        Get the correct git branch name for a submission.

        Raises:
            ValueError: if no forge can be found.
        """
        msg = email.message_from_string(submission.headers)
        for branch in self.branches.all():
            if re.search(
                branch.subject_match, msg["Subject"], flags=re.MULTILINE | re.IGNORECASE
            ):
                return branch.name
        else:
            raise ValueError(f"No branch matches {submission}")


class Branch(models.Model):
    """
    Models multiple development branches within a single tree.

    For example, a tree might have a feature branch and a bugfix branch and
    patches may apply to only one or the other. This allows us to route patches
    based on subject prefixes to the appropriate branch.
    """

    git_forge = models.ForeignKey(
        GitForge, on_delete=models.CASCADE, related_name="branches"
    )
    subject_prefix = models.CharField(
        max_length=64,
        help_text="The prefix to include in emails in addition to "
        "'PATCHvN'. The default is no prefix.",
        blank=True,
        default="",
    )

    subject_match = models.CharField(
        max_length=64,
        blank=True,
        default="",
        validators=[validate_regex_compiles],
        help_text="Regex to match the "
        "subject against if the Patchwork project maps to multiple development "
        "branches. That is, perhaps you have a project where patches are "
        "prefixed with PROJ FEATURE for features and PROJ BUGFIX for bugfixes "
        "and pull requests should be opened against different branches depending "
        "on whether the patch is a feature or a bugfix. Like the project match, "
        "this will be used with IGNORECASE and MULTILINE flags. The first git "
        "forge returned from the database with a matching rule is used.",
    )
    name = models.CharField(
        max_length=255,
        default="master",
        help_text="The development branch name; "
        "This is used to determine the email prefix when bridging a merge request "
        "to email, as well as the correct branch to apply incoming patches to "
        "when bridging email to merge requests",
    )

    class Meta:
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return f"The '{self.name}' branch in {self.git_forge}"

    def __repr__(self):
        return (
            f"Branch(name={self.name}, subject_match={self.subject_match}, "
            f"subject_prefix={self.subject_prefix}, "
            f"git_forge={repr(self.git_forge)})"
        )
