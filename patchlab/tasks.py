# SPDX-License-Identifier: GPL-2.0-or-later
import logging
import os

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from billiard.process import current_process
from patchwork.models import Series
from patchwork import models as pw_models
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
        _log.error("No git forge associated with %s", str(series.project))
        return

    # This assumes Celery has been configured with an acceptable working directory
    # either via the systemd unit file or the celery worker argument.
    working_dir = os.path.join(os.getcwd(), str(current_process().name))
    if not os.path.exists(working_dir):
        os.mkdir(working_dir)
    try:
        email_bridge.open_merge_request(gitlab, series, working_dir)
    except Exception as e:
        _log.warning("Failed to open merge request, retry in 1 minute")
        raise open_merge_request.retry(exc=e, throw=False, countdown=60)


@shared_task
def submit_gitlab_comment(comment_id: int) -> None:
    """Submit an emailed comment as a Gitlab comment."""
    try:
        comment = pw_models.Comment.objects.get(pk=comment_id)
    except pw_models.Comment.DoesNotExist:
        _log.info("Received invalid comment id %d, dropping task", comment_id)
        return

    try:
        gitlab = gitlab_module.Gitlab.from_config(
            comment.submission.project.git_forge.host
        )
    except gitlab_module.config.ConfigError:
        _log.error(
            "Missing Gitlab configuration for %s; skipping comment %i",
            comment.submission.project.git_forge.host,
            comment.msgid,
        )
        return

    email_bridge.submit_gitlab_comment(gitlab, comment)


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
    try:
        gitlab2email.email_merge_request(gitlab, project_id, merge_id)
    except Exception as e:
        _log.warning(
            "Failed to email merge request from merge_request_hook, retrying in 1 minute"
        )
        raise merge_request_hook.retry(exc=e, throw=False, countdown=60)


@shared_task
def email_comment(
    gitlab_host: str, project_id: int, comment_author, comment, merge_id=None,
):
    try:
        gitlab = gitlab_module.Gitlab.from_config(gitlab_host)
    except gitlab_module.config.ConfigError:
        _log.error("Missing Gitlab configuration for %s", gitlab_host)
        return
    try:
        gitlab2email.email_comment(
            gitlab, project_id, comment_author, comment, merge_id
        )
    except Exception as e:
        _log.warning("Failed to send gitlab comment as email, retrying...")
        raise merge_request_hook.retry(exc=e, throw=False, countdown=60)
