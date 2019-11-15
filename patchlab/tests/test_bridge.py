from email import message_from_string
from unittest import mock

from celery import exceptions as celery_exceptions
from django.core import mail
from django.test import override_settings
from patchwork.parser import parse_mail
from patchwork import models as pw_models
import gitlab as gitlab_module

from .. import bridge, models
from . import (
    SINGLE_PATCH_GIT_AM_FAILURE,
    MULTI_PATCH_GIT_AM_FAILURE,
    MULTI_COMMIT_MR,
    SINGLE_COMMIT_MR,
    BaseTestCase,
)


class OpenMergeRequestTests(BaseTestCase):
    @classmethod
    def setUpTestData(cls):

        pw_models.State(ordering=0, name="test").save()
        cls.project = pw_models.Project.objects.create(
            linkname="patchlab_test",
            name="patchlab_test",
            listid="patchlab.example.com",
            listemail="patchlab@patchlab.example.com",
            web_url="https://gitlab/root/patchlab_test/",
            scm_url="https://gitlab/root/patchlab_test.git",
        )
        cls.forge = models.GitForge.objects.create(
            project=cls.project, host="gitlab", forge_id=1,
        )
        cls.branch = models.Branch.objects.create(
            git_forge=cls.forge, subject_prefix="TEST PATCH", name="master",
        )
        parse_mail(message_from_string(SINGLE_COMMIT_MR), "patchlab.example.com")
        cls.gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="xTzqx9yQzAJtaj-sG8yJ", ssl_verify=False
        )

    @mock.patch("patchlab.bridge._create_remote_branch")
    def test_success(self, mock_create_remote_branch):
        """Assert submissions can be successfully bridged to a merge request."""
        series = pw_models.Series.objects.get(pk=1)

        bridge.open_merge_request(self.gitlab, series, "some/dir")

        bridged_submissions = models.BridgedSubmission.objects.all()
        self.assertEqual(1, len(bridged_submissions))

    def test_gitlab_get_server_failure(self):
        """
        Assert server errors result in Retry exceptions.

        The VCR for this test results in an HTTP 502 for the initial request for the project.
        """
        self.assertRaises(
            celery_exceptions.Retry,
            bridge.open_merge_request,
            self.gitlab,
            pw_models.Series.objects.get(pk=1),
            "some/dir",
        )

    def test_gitlab_get_client_failure(self):
        """Assert client errors result in fatal exceptions."""
        series = pw_models.Series.objects.get(pk=1)
        series.project.git_forge.forge_id = 2
        self.assertRaises(
            gitlab_module.exceptions.GitlabGetError,
            bridge.open_merge_request,
            self.gitlab,
            series,
            "some/dir",
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
