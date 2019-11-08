import time

from django.core.management.base import BaseCommand, CommandError
from patchwork.models import Project
import gitlab as gitlab_module

from patchlab.bridge import pr_exists, open_merge_request, session, poll_events


class Command(BaseCommand):
    help = "Covert emailed patches to GitLab merge requests"

    def add_arguments(self, parser):
        parser.add_argument("project", help="Patchwork project name")
        parser.add_argument(
            "api_url", help="The Patchwork API URL (e.g. http://localhost/api/1.1"
        )
        parser.add_argument("-c", "--config", help="Gitlab configuration file")

    def handle(self, *args, **kwargs):
        try:
            project = Project.objects.get(name=kwargs["project"])
        except Project.DoesNotExist:
            raise CommandError("No such project exists in Patchwork")
        try:
            gitlab = gitlab_module.Gitlab.from_config(
                project.git_forge.host, kwargs["config"]
            )
        except gitlab_module.config.ConfigError as e:
            raise CommandError(
                f"Gitlab configuration error for host {project.git_forge.host}: {str(e)}"
            )

        try:
            with open("last_event", "r") as f:
                since = f.read()
        except IOError:
            since = None

        while True:
            for event in poll_events(kwargs["api_url"], project, since):
                branch_name = f'emails/series-{event["payload"]["series"]["id"]}'
                mbox = session.get(event["payload"]["series"]["mbox"], timeout=30)
                if not pr_exists(gitlab, project.git_forge.forge_id, branch_name):
                    open_merge_request(
                        project,
                        event["payload"]["series"]["name"],
                        branch_name,
                        mbox.text,
                    )

                with open("last_event", "w") as f:
                    f.write(event["date"])
            time.sleep(60)
