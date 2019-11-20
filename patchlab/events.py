# SPDX-License-Identifier: GPL-2.0-or-later
import email
import logging

from django.db.models.signals import post_save
from patchwork.models import Patch

from .tasks import open_merge_request

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

    # Make sure we don't bridge merge requests back to merge requests
    mail_headers = email.message_from_string(instance.headers)
    if "X-Patchlab-Merge-Request" in mail_headers:
        _log.info("Ignoring instance %d as it originated from the bridge.", instance.id)
        return

    try:
        open_merge_request.apply_async((instance.series.id,))
    except Exception:
        _log.exception(
            "Failed to open merge request for series id %i in %s",
            instance.series.pk,
            str(instance.series.project),
        )
        return


post_save.connect(patch_event_handler, sender=Patch, dispatch_uid="patchlab_mr")
