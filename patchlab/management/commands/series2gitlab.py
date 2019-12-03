# SPDX-License-Identifier: GPL-2.0-or-later
from django.core.management.base import BaseCommand, CommandError

from patchlab.tasks import open_merge_request


class Command(BaseCommand):
    help = (
        "Covert a patch series to GitLab merge requests; this should happen"
        " automatically, but if recovering from a crash in the automated handler"
        " during mail import, this can be useful."
    )

    def add_arguments(self, parser):
        parser.add_argument("series", help="The series id in Patchwork")

    def handle(self, *args, **kwargs):
        try:
            open_merge_request.apply_async((kwargs["series"],))
        except Exception as e:
            raise CommandError(f"Failed to open merge request: {str(e)}")
