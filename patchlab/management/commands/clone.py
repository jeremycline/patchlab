# SPDX-License-Identifier: GPL-2.0-or-later
import os
import subprocess

from django.core.management.base import BaseCommand, CommandError
from patchwork.models import Project


class Command(BaseCommand):
    help = "Set up a project repository for pushing merge requests."

    def add_arguments(self, parser):
        parser.add_argument("project", help="Patchwork project name")
        parser.add_argument(
            "clone_url",
            help=(
                "The git clone URL; this should allow writing to the remote. For GitLab,"
                " the URL might be in the form "
                "https://oauth2:<token-with-write_repository>@host/user/repo.git"
            ),
        )
        parser.add_argument(
            "-t",
            "--timeout",
            help=(
                "The maximum time to wait for the clone to complete in seconds "
                "(default is 30 minutes)"
            ),
            default=60 * 30,
        )

    def handle(self, *args, **kwargs):
        try:
            project = Project.objects.get(name=kwargs["project"])
        except Project.DoesNotExist:
            raise CommandError("No such project exists in Patchwork")

        if not os.path.exists(project.git_forge.repo_path):
            if not os.access(os.path.dirname(project.git_forge.repo_path), os.W_OK):
                raise CommandError(
                    "User needs write access to {project.git_forge.repo_path}"
                )

            subprocess.run(
                ["git", "clone", kwargs["clone_url"], project.git_forge.repo_path],
                check=True,
                timeout=kwargs["timeout"],
            )
