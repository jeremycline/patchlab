from django.db.models.signals import post_save

from patchwork.models import Patch

from .models import GitForge


def open_merge_request(sender, **kwargs):
    """
    A post-save signal handler to open a pull request whenever a patch series
    is received.

    Args:
        sender (Patch): The model class that was saved.
    """
    print("Opening pull request...")
    instance = kwargs["instance"]
    created = kwargs["created"]

    # TODO figure out if/when patches are modified
    if not created:
        return

    # TODO why is the series field nullable?
    if not (instance.series and instance.series.received_all):
        return

    # Apply patches to the local clone, git push using the API token we have
    # TODO write model mapping gitlab project to a patchwork Project to store
    # API tokens, SCM url(s), etc.
    patches = instance.series.patches.all()

    # TODO handle missing etc
    forge = GitForge.objects.get(project=instance.project.patch_project)

    # git am on forge.path, push -o pr using the token from GitForge


post_save.connect(open_merge_request, sender=Patch, dispatch_uid="patchlab_mr")
