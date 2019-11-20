# SPDX-License-Identifier: GPL-2.0-or-later
import logging
import os

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from billiard.process import current_process
from patchwork.models import Series
import gitlab as gitlab_module

from patchlab import bridge as email_bridge, gitlab2email

_log = logging.getLogger(__name__)


@shared_task
def open_merge_request(series_id: int) -> None:
    """Convert a Patchwork series into a pull request in GitLab."""
    series = Series.objects.get(pk=series_id)
    try:
        gitlab = gitlab_module.Gitlab.from_config(series.project.git_forge.host)
    except gitlab_module.config.ConfigError:
        _log.error(
            "Missing Gitlab configuration for %s; skipping series %i",
            series.project.git_forge.host,
            series_id,
        )
        return
    except ObjectDoesNotExist:
        _log.error(
            "No git forge associated with %s", str(series.project),
        )
        return

    # This assumes Celery has been configured with an acceptable working directory
    # either via the systemd unit file or the celery worker argument.
    working_dir = os.path.join(os.getcwd(), str(current_process().name))
    if not os.path.exists(working_dir):
        os.mkdir(working_dir)

    email_bridge.open_merge_request(gitlab, series, working_dir)


@shared_task
def merge_request_hook(gitlab_host: str, project_id: int, merge_id: int) -> None:
    """
    Handle incoming merge request web hooks.

    If a merge request is made up of more than a single commit, a cover letter
    is created using the merge request description.

    Args:
        merge_request: The merge request web hook payload from GitLab
    """
    gitlab = gitlab_module.Gitlab.from_config(gitlab_host)
    gitlab2email.email_merge_request(gitlab, project_id, merge_id)


@shared_task
def email_comment(comment):
    pass
