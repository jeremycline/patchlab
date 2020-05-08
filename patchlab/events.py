# SPDX-License-Identifier: GPL-2.0-or-later
import email
import logging

from django.conf import settings
from django.db.models.signals import post_save
from patchwork.models import Comment, Patch

from .tasks import open_merge_request, submit_gitlab_comment

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


def comment_event_handler(sender, **kwargs):
    """
    A signal handler that bridges emailed comments to a merge request, if one
    exists.
    """
    # Make sure we don't bridge comments back to GitLab
    mail_headers = email.message_from_string(kwargs["instance"].headers)
    if "X-Patchlab-Comment" in mail_headers:
        _log.info(
            "Ignoring instance %d as it originated from the bridge.",
            kwargs["instance"].id,
        )
        return

    try:
        submit_gitlab_comment.apply_async((kwargs["instance"].id,))
    except Exception:
        _log.exception("Failed to dispatch task for comment %d", kwargs["instance"].id)


if settings.PATCHLAB_EMAIL_TO_GITLAB_MR:
    post_save.connect(patch_event_handler, sender=Patch, dispatch_uid="patchlab_mr")

if settings.PATCHLAB_EMAIL_TO_GITLAB_COMMENT:
    post_save.connect(
        comment_event_handler, sender=Comment, dispatch_uid="patchlab_comments"
    )
