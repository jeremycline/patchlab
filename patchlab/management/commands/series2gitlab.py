# SPDX-License-Identifier: GPL-2.0-or-later
from django.core.management.base import BaseCommand, CommandError
from patchwork.models import Project
import gitlab as gitlab_module

from patchlab.bridge import open_merge_request


class Command(BaseCommand):
    help = (
        "Covert a patch series to GitLab merge requests; this should happen"
        " automatically, but if recovering from a crash in the automated handler"
        " during mail import, this can be useful."
    )

    def add_arguments(self, parser):
        parser.add_argument("project", help="Patchwork project name")
        parser.add_argument("series", help="The series id in Patchwork")

    def handle(self, *args, **kwargs):
        try:
            project = Project.objects.get(name=kwargs["project"])
        except Project.DoesNotExist:
            raise CommandError("No such project exists in Patchwork")
        try:
            gitlab = gitlab_module.Gitlab.from_config(project.git_forge.host)
        except gitlab_module.config.ConfigError as e:
            raise CommandError(
                f"Gitlab configuration error for host {project.git_forge.host}: {str(e)}"
            )

        try:
            open_merge_request(gitlab, project, kwargs["series"])
        except Exception as e:
            raise CommandError(f"Failed to open merge request: {str(e)}")
