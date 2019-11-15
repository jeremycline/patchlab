# SPDX-License-Identifier: GPL-2.0-or-later

import logging

from django.apps import AppConfig
from django.urls import include, path

_log = logging.getLogger(__name__)


class PatchlabConfig(AppConfig):
    """
    Django app configuration.

    This class provides application configuration as well as a number of hooks
    for application initialization. Refer to documentation at
    https://docs.djangoproject.com/en/dev/ref/applications/ for available hooks.
    """

    name = "patchlab"

    def ready(self):
        from django.conf import settings
        from patchwork import urls

        from . import urls as our_urls
        from . import events  # noqa: F401

        urls.urlpatterns.append(path("patchlab/", include(our_urls.urlpatterns)))

        # Make sure admins set a secret token
        if settings.PATCHLAB_GITLAB_WEBHOOK_SECRET == "change this":
            _log.error(
                "Using the default GitLab web hook secret; this is not safe"
                " for production deployments!"
            )
