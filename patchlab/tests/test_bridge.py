from email import message_from_string
from unittest import mock

from celery import exceptions as celery_exceptions
from django.core import mail
from django.test import override_settings
from patchwork.parser import parse_mail
from patchwork import models as pw_models
import gitlab as gitlab_module

from .. import bridge, models
from . import BaseTestCase


class OpenMergeRequestTests(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
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
        self.maxDiff = None
        super().setUp()
        try:
            mail.outbox.clear()
        except AttributeError:
            pass

    def test_single_patch(self, mock_run):
        """Assert single patches that don't apply result in useful error emails."""
        mock_run.return_value.stdout = "abc123"
        expected_message = """
Hello,

We were unable to apply this patch series to the current development branch.
The current head of the master branch is commit abc123.

Please rebase this series against the current development branch and resend it
or, if you prefer never seeing this email again, submit your series as a pull
request:

  1. Create an account and fork https://gitlab/root/patchlab_test/.
  2. git remote add <remote-name> <your-forked-repo>
  3. git push <remote-name> <branch-name> --push-option=merge_request.create \\
       --push-option=merge_request.title="[TEST] Bring balance to the equals signs"
"""

        bridge._notify_am_failure(
            models.GitForge.objects.first(), pw_models.Series.objects.get(pk=1)
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(expected_message, mail.outbox[0].body)
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
        expected_message = """
Hello,

We were unable to apply this patch series to the current development branch.
The current head of the master branch is commit abc123.

Please rebase this series against the current development branch and resend it
or, if you prefer never seeing this email again, submit your series as a pull
request:

  1. Create an account and fork https://gitlab/root/patchlab_test/.
  2. git remote add <remote-name> <your-forked-repo>
  3. git push <remote-name> <branch-name> --push-option=merge_request.create \\
       --push-option=merge_request.title="Update the README in two un-atomic commits"
"""

        bridge._notify_am_failure(
            models.GitForge.objects.first(), pw_models.Series.objects.get(pk=2)
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(expected_message, mail.outbox[0].body)
        self.assertEqual(
            "<157530798430.5472.9327296165743891677@patchwork>",
            mail.outbox[0].extra_headers["In-Reply-To"],
        )
        self.assertEqual(
            "Re: Update the README in two un-atomic commits", mail.outbox[0].subject
        )
        self.assertEqual(["patchwork@patchwork.example.com"], mail.outbox[0].to)


class SubmitGitlabCommentTests(BaseTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="xTzqx9yQzAJtaj-sG8yJ", ssl_verify=False
        )

    def test_ack_bridged(self):
        """Assert Acked-by tags are bridged as labels."""
        comment = """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Re: [TEST PATCH] Bring balance to the equals signs
From: Jeremy Cline <jcline@redhat.com>
To: patchlab@patchlab.example.com
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <6@localhost.localdomain>
X-Patchlab-Patch-Author: Jeremy Cline <jcline@redhat.com>
X-Patchlab-Merge-Request: https://gitlab/root/patchlab_test/merge_requests/1
X-Patchlab-Commit: a958a0dff5e3c433eb99bc5f18cbcfad77433b0d
In-Reply-To: <4@localhost.localdomain>
List-Id: patchlab.example.com

Hi,

> From: Jeremy Cline <jcline@redhat.com>
>
> This is a silly change so I can write a test.
>
> Signed-off-by: Jeremy Cline <jcline@redhat.com>

Incredible work.

Acked-by: Jeremy Cline <jcline@redhat.com>
"""
        parse_mail(message_from_string(comment), "patchlab.example.com")
        comment = pw_models.Comment.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=models.GitForge.objects.get(pk=1),
            submission=comment.submission,
            merge_request=2,
        )

        merge_request, note = bridge.submit_gitlab_comment(self.gitlab, comment)

        self.assertEqual(merge_request.labels, ["Acked-by: jcline@redhat.com"])

    def test_nack_bridged(self):
        """Assert Nacked-by tags are bridged as labels."""
        comment = """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Re: [TEST PATCH] Bring balance to the equals signs
From: Jeremy Cline <jcline@redhat.com>
To: patchlab@patchlab.example.com
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <6@localhost.localdomain>
X-Patchlab-Patch-Author: Jeremy Cline <jcline@redhat.com>
X-Patchlab-Merge-Request: https://gitlab/root/patchlab_test/merge_requests/1
X-Patchlab-Commit: a958a0dff5e3c433eb99bc5f18cbcfad77433b0d
In-Reply-To: <4@localhost.localdomain>
List-Id: patchlab.example.com

Hi,

> From: Jeremy Cline <jcline@redhat.com>
>
> This is a silly change so I can write a test.
>
> Signed-off-by: Jeremy Cline <jcline@redhat.com>

This is unacceptable.

Nacked-by: Jeremy Cline <jcline@redhat.com>
"""
        parse_mail(message_from_string(comment), "patchlab.example.com")
        comment = pw_models.Comment.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=models.GitForge.objects.get(pk=1),
            submission=comment.submission,
            merge_request=2,
        )

        merge_request, note = bridge.submit_gitlab_comment(self.gitlab, comment)

        self.assertEqual(merge_request.labels, ["Nacked-by: jcline@redhat.com"])
