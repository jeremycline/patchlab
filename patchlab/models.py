from django.core import validators
from django.db import models


class GitForge(models.Model):
    """
    Map the Git forge to a Patchwork project.

    Attributes:
        project (patchwork.models.Project): The Patchwork project this is
            associated with.
        upstream_scm (str): The upstream SCM URL where pull requests should
            be sent.
        branch_scm (str): The SCM URL where we store branches we create from email.
            This may be the same as the upstream URL.
        access_token (str): The API token to write to the branch_scm repository.
        path (str): The filesystem path where the local clone of the branch_scm
            is located.
    """
    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="project"
    )
    upstream_scm = models.URLField(
        verbose_name="Upstream SCM URL",
        max_length=2000,
        validators=validators.URLValidator(schemes=["https", "ssh", "git"]),
    )
    branch_scm = models.URLField(
        verbose_name="Forked repository SCM URL",
        max_length=2000,
        validators=validators.URLValidator(schemes=["https", "ssh", "git"]),
    )
    access_token = models.CharField(max_length=255)
    path = models.FilePathField()
