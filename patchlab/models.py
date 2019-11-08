import os

from django.conf import settings
from django.db import models

from patchwork.models import Project, Submission


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
    commit = models.CharField(max_length=128, unique=True, null=True, blank=True)


class GitForge(models.Model):
    """
    Represents a Git forge being bridged to and from email.

    Attributes:
        project: A one-to-one relationship with a
            :class:`patchwork.models.Project`.
        host: The hostname of the Git forge; this is used for a uniqueness
            constraint on it combined with the forge ID.
        forge_id: The unique ID of the project in the Git forge. For Gitlab,
            this is prominently displayed on the project home page.
        subject_prefix: The subject prefix to prepend to patches being sent
            to the list.
        development_branch: The branch in the Git forge used for development;
            this is the branch pull requests are opened against.
    """

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="git_forge", primary_key=True
    )
    host = models.CharField(max_length=255)
    forge_id = models.IntegerField()
    subject_prefix = models.CharField(max_length=64)
    development_branch = models.CharField(max_length=255, default="master")

    class Meta:
        unique_together = [["host", "forge_id"]]

    def __str__(self):
        return (
            f"{self.project.name} hosted on {self.host} as project "
            f" ID {self.project_id}"
        )

    def __repr__(self):
        return (
            f"GitForge(host={self.host}, forge_id={self.forge_id}, "
            f"subject_prefix={self.subject_prefix}, "
            f"project={repr(self.project)})"
        )

    @property
    def repo_path(self):
        return os.path.join(settings.PATCHLAB_REPO_DIR, f"{self.host}-{self.forge_id}")
