from django.db import models

from patchwork.models import Project, Submission


class BridgedSubmission(models.Model):
    """
    Information about Patchwork submissions we've bridged back and forth.

    This is necessary so that comments converted to email are properly threaded.
    """

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, primary_key=True
    )
    merge_request = models.IntegerField(null=False, blank=False)
    commit = models.CharField(max_length=128, unique=True, null=True, blank=True)


class GitForge(models.Model):
    """Represents a Git forge being bridged to and from email."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE, primary_key=True)
    host = models.CharField(max_length=255)
    forge_id = models.IntegerField()
    subject_prefix = models.CharField(max_length=64)

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
