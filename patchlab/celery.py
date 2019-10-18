import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patchlab.settings")

#: The celery application object
app = Celery("patchlab")
app.config_from_object("django.conf.settings", namespace="CELERY")
app.autodiscover_tasks()
