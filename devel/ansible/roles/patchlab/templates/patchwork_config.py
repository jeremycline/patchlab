"""Settings for the CI test environment."""
import os

from patchwork.settings.base import *  # noqa
from patchlab.settings.base import *  # noqa

DEBUG = False
SECRET_KEY = "{{ vault_patchwork_secret_key }}"

INSTALLED_APPS.append("patchlab")  # noqa

CELERY_RESULT_BACKEND = "amqp://"
CELERY_BROKER_URL = "amqp://"

# Email
EMAIL_HOST = "{{ patchwork_email_host }}"
EMAIL_PORT = {{ patchwork_email_port }}
EMAIL_HOST_USER = "{{ patchwork_email_user }}"
EMAIL_HOST_PASSWORD = "{{ patchwork_email_password }}"
EMAIL_USE_TLS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = "{{ patchwork_default_from_email }}"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
NOTIFICATION_FROM_EMAIL = DEFAULT_FROM_EMAIL

ADMINS = (
    # Add administrator contact details in the form:
    # ('Jeremy Kerr', 'jk@ozlabs.org'),
)

ALLOWED_HOSTS = ["{{ patchlab_fqdn }}"]

# Database
#
# If you're using a postgres database, connecting over a local unix-domain
# socket, then the following setting should work for you. Otherwise,
# see https://docs.djangoproject.com/en/2.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("DATABASE_NAME", "patchwork"),
        "USER": os.environ.get("DATABASE_USER", "patchwork"),
        "PASSWORD": os.environ.get(
            "DATABASE_PASSWORD", "{{ vault_patchwork_database_password }}"
        ),
    },
}

STATIC_ROOT = "/var/www/patchwork/static/"
STATIC_URL = "/static/"

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

#
# Static files settings
# https://docs.djangoproject.com/en/2.2/ref/settings/#static-files
# https://docs.djangoproject.com/en/2.2/ref/contrib/staticfiles/#manifeststaticfilesstorage
#

PATCHLAB_EMAIL_TO_GITLAB_MR = True
PATCHLAB_EMAIL_TO_GITLAB_COMMENT = True
PATCHLAB_IGNORE_GITLAB_LABELS = ["🛑 Do Not Email", "Do Not Email"]
PATCHLAB_CC_FILTER = r"@(redhat.com|fedoraproject.org)$"
PATCHLAB_FROM_EMAIL = "{{ patchlab_from_email }}"

PATCHLAB_GITLAB_WEBHOOK_SECRET = "{{ vault_patchlab_gitlab_webhook_secret }}"
PATCHLAB_REPO_DIR = "/var/lib/patchlab"
PATCHLAB_MAX_EMAILS = 10

#: A boolean that indicates whether or not to wait for the merge request's Pipeline
#: to complete successfully before emailing the merge request.
PATCHLAB_PIPELINE_SUCCESS_REQUIRED = True
#: The number of minutes, as an integer, to wait for the pipeline to complete.
PATCHLAB_PIPELINE_MAX_WAIT = 60
