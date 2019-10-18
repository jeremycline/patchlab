from django.apps import AppConfig
from django.urls import include, path


class PatchlabConfig(AppConfig):
    """
    Django app configuration.

    This class provides application configuration as well as a number of hooks
    for application initialization. Refer to documentation at
    https://docs.djangoproject.com/en/dev/ref/applications/ for available hooks.
    """

    name = "patchlab"

    def ready(self):
        from . import urls as our_urls
        from patchwork import urls

        urls.urlpatterns.append(path("patchlab/", include(our_urls.urlpatterns)))
