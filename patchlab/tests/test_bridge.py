from email import message_from_string
from unittest import mock

from django.core import mail
from django.test import override_settings

from patchwork.parser import parse_mail
from patchwork import models as pw_models

from .. import bridge, models
from . import (
    SINGLE_PATCH_GIT_AM_FAILURE,
    MULTI_PATCH_GIT_AM_FAILURE,
    MULTI_COMMIT_MR,
    SINGLE_COMMIT_MR,
    BaseTestCase,
)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@mock.patch("patchlab.bridge.subprocess.run")
class NotifyAmFailureTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        try:
            mail.outbox.clear()
        except AttributeError:
            pass

        pw_models.State(ordering=0, name="test").save()
        self.project = pw_models.Project.objects.create(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
            web_url="https://gitlab.example.com/root/kernel",
        )
        self.forge = models.GitForge.objects.create(
            project=self.project, host="gitlab.example.com", forge_id=1,
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="TEST PATCH", name="master",
        )

    def test_single_patch(self, mock_run):
        """Assert single patches that don't apply result in useful error emails."""
        mock_run.return_value.stdout = "abc123"
        parse_mail(
            message_from_string(SINGLE_COMMIT_MR), "kernel.lists.fedoraproject.org"
        )

        bridge._notify_am_failure(self.forge, pw_models.Series.objects.all()[0])

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(SINGLE_PATCH_GIT_AM_FAILURE, mail.outbox[0].body)
        self.assertEqual(
            "<4@localhost.localdomain>", mail.outbox[0].extra_headers["In-Reply-To"]
        )
        self.assertEqual(
            "Re: [TEST] Bring balance to the equals signs", mail.outbox[0].subject
        )
        self.assertEqual(["patchwork@patchwork.example.com"], mail.outbox[0].to)

    def test_multi_patch_series(self, mock_run):
        """Assert multi-patch series with cover letters respond to the cover letter."""
        mock_run.return_value.stdout = "abc123"
        for email in MULTI_COMMIT_MR:
            parse_mail(message_from_string(email), "kernel.lists.fedoraproject.org")

        bridge._notify_am_failure(self.forge, pw_models.Series.objects.all()[0])

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(MULTI_PATCH_GIT_AM_FAILURE, mail.outbox[0].body)
        self.assertEqual(
            "<1@localhost.localdomain>", mail.outbox[0].extra_headers["In-Reply-To"]
        )
        self.assertEqual("Re: Update the README", mail.outbox[0].subject)
        self.assertEqual(["patchwork@patchwork.example.com"], mail.outbox[0].to)
