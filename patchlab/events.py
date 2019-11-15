# SPDX-License-Identifier: GPL-2.0-or-later
import logging

from django.db.models.signals import post_save
from patchwork.models import Patch
import gitlab as gitlab_module

from .bridge import open_merge_request

_log = logging.getLogger(__name__)


def patch_event_handler(sender, **kwargs):
    """
    A post-save signal handler to open a pull request whenever a patch series
    is received.

    Args:
        sender (Patch): The model class that was saved.
    """
    instance = kwargs["instance"]

    if not (instance.series and instance.series.received_all):
        return

    project = instance.series.project
    try:
        gitlab = gitlab_module.Gitlab.from_config(project.git_forge.host)
    except gitlab_module.config.ConfigError:
        _log.error(
            "Missing Gitlab configuration for %s; skipping series %i",
            project.git_forge.host,
            instance.series.pk,
        )
        return

    try:
        open_merge_request(gitlab, project, instance.series.id)
    except Exception:
        _log.exception(
            "Failed to open merge request for series id %i in %s",
            instance.series.pk,
            str(project),
        )
        return


post_save.connect(patch_event_handler, sender=Patch, dispatch_uid="patchlab_mr")
