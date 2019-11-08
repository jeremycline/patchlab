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
