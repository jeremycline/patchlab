"""Settings for the CI test environment."""
import os

from patchwork.settings.dev import *  # noqa

from .base import *  # noqa
from ..tests import FIXTURES

INSTALLED_APPS.append("patchlab")  # noqa

# Alter the default database to Postgres.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "HOST": os.getenv("PW_TEST_DB_HOST", "localhost"),
        "PORT": os.getenv("PW_TEST_DB_PORT", ""),
        "USER": os.getenv("PW_TEST_DB_USER", "postgres"),
        "PASSWORD": os.getenv("PW_TEST_DB_PASS", "password"),
        "NAME": os.getenv("PW_TEST_DB_NAME", "patchwork"),
        "TEST": {"CHARSET": "utf8"},
    }
}

FIXTURE_DIRS = [os.path.join(FIXTURES, "db")]
PATCHLAB_PIPELINE_SUCCESS_REQUIRED = True
