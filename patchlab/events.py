from django.db.models.signals import post_save
from patchwork.models import Patch
from patchwork.views import utils

from .bridge import open_merge_request


# TODO probably just hook onto the event model and look for series complete
def patch_event_handler(sender, **kwargs):
    """
    A post-save signal handler to open a pull request whenever a patch series
    is received.

    Args:
        sender (Patch): The model class that was saved.
    """
    instance = kwargs["instance"]
    created = kwargs["created"]

    # TODO figure out if/when patches are modified
    if not created:
        return
    # TODO why is the series field nullable?
    if not (instance.series and instance.series.received_all):
        return

    mbox = utils.series_to_mbox(instance.series)
    branch_name = f"email/series-{instance.series.id}"
    open_merge_request(instance.series.title, branch_name, mbox)


post_save.connect(patch_event_handler, sender=Patch, dispatch_uid="patchlab_mr")
