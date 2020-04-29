"""
Django settings specific to Patchlab.

Patchlab is intended to be run as an extension to Patchwork, so you should
start with a valid `patchwork configuration`_ and include the settings
documented here in that file.

.. note:: Don't forget to add Patchlab to the INSTALLED_APPS list. If you're
    using the production.example.py settings file provided by Patchwork as
    the starting point, adding ``INSTALLED_APPS.append("patchlab")`` to the
    end of the file is enough.

Patchlab uses Django's builtin email framework so be sure include email related
`Django settings`_.

.. _patchwork configuration: https://patchwork.readthedocs.io/en/latest/deployment/configuration/
.. _Django settings: https://docs.djangoproject.com/en/stable/ref/settings/
"""

#: The secret token GitLab is configured to send with the web hook. Patchlab
#: uses this to validate the received payload. This should be a securely
#: generated random string.
PATCHLAB_GITLAB_WEBHOOK_SECRET = "change this"

#: The maximum number of emails to send out when bridging a merge request to
#: the mailing list. This can be helpful to avoid sending patch series that are
#: many thousands of commits accidentally. If the number of commits in a merge
#: request exceed this number, an email with instructions on how to pull the
#: git branch for local review is sent instead of the series.
PATCHLAB_MAX_EMAILS = 25

#: The directory to store Git trees in. The scheme inside this directory is
#: <forge-host>-<forge-id>.
PATCHLAB_REPO_DIR = "/var/lib/patchlab"

#: If true, Patchlab will bridge patch series discovered by Patchwork to Gitlab
#: merge requests.
PATCHLAB_EMAIL_TO_GITLAB_MR = True

#: If true, Patchlab will bridge emailed comments to patch series in addition
#: to patches.
PATCHLAB_EMAIL_TO_GITLAB_COMMENT = True

#: A list of labels that, if any are present on a merge request, are ignored.
PATCHLAB_IGNORE_GITLAB_LABELS = ["🛑 Do Not Email", "Do Not Email"]

#: A regular expression run against emails in the Cc: labels on merge requests
#: that must match for the email to be included in the list of Ccs.
PATCHLAB_CC_FILTER = r""

#: If True, emails will only be sent if a merge request's pipeline succeeds.
PATCHLAB_PIPELINE_SUCCESS_REQUIRED = False

#: If PATCHLAB_PIPELINE_SUCCESS_REQUIRED = True, the max time in minutes to wait
#: for a pipeline to complete. Defaults to 2 hours.
PATCHLAB_PIPELINE_MAX_WAIT = 120

#: The email to use for From: in bridged comments and patches. Python's
#: `format` API will be called on the string. Currently the only key provided is
#: `forge_author` which is set to the user's name on the Git forge.
PATCHLAB_FROM_EMAIL = "Email Bridge on behalf of {forge_user} <bridge@example.com>"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "celery": {"handlers": ["console"], "level": "INFO"},
        "patchwork": {"handlers": ["console"], "level": "INFO"},
        "patchlab": {"handlers": ["console"], "level": "INFO"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
