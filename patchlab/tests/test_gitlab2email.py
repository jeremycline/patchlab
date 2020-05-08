from unittest import mock
import os
import json

from django.core import mail
from django.test import override_settings
from patchwork import models as pw_models
import gitlab as gitlab_module

from patchlab import gitlab2email, models
from . import BIG_EMAIL, SINGLE_COMMIT_MR, MULTI_COMMIT_MR, BaseTestCase, FIXTURES


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailMergeRequestTests(BaseTestCase):
    """
    Tests for the :func:`gitlab2email.email_merge_request` function. Many tests
    rely on the VCR recording to alter the outcome of the test.
    """

    def setUp(self):
        super().setUp()
        try:
            mail.outbox.clear()
        except AttributeError:
            pass

    @mock.patch("patchlab.gitlab2email._log")
    def test_label_in_ignored_labels(self, mock_log):
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="xTzqx9yQzAJtaj-sG8yJ", ssl_verify=False
        )

        gitlab2email.email_merge_request(gitlab, 1, 8)

        mock_log.info.assert_called_once_with(
            "Not emailing %r as it is labeled with the %s label, which is ignored.",
            mock.ANY,
            "🛑 Do Not Email",
        )

    @mock.patch("patchlab.gitlab2email._log")
    def test_branch_unmergeable(self, mock_log):
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="xTzqx9yQzAJtaj-sG8yJ", ssl_verify=False
        )

        gitlab2email.email_merge_request(gitlab, 1, 8)

        mock_log.info.assert_called_once_with(
            "Not emailing %r because it can't be merged", mock.ANY
        )

    @mock.patch("patchlab.gitlab2email._log")
    def test_work_in_progress(self, mock_log):
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="xTzqx9yQzAJtaj-sG8yJ", ssl_verify=False
        )

        gitlab2email.email_merge_request(gitlab, 1, 8)

        mock_log.info.assert_called_once_with(
            "Not emailing %r because it's a work in progress", mock.ANY
        )


class RerollTests(BaseTestCase):
    """Tests for the :func:`gitlab2email._reroll` function."""

    def test_no_prior_submissions(self):
        """Assert if there are no prior submissions, the version is 1."""
        git_forge = models.GitForge.objects.get(pk=1)
        merge_request = mock.Mock(iid=42)

        version, in_reply_to = gitlab2email._reroll(git_forge, merge_request)

        self.assertEqual(1, version)
        self.assertIsNone(in_reply_to)

    def test_missing_series_version(self):
        """Assert if there the series_version is null the version is 1."""
        git_forge = models.GitForge.objects.get(pk=1)
        merge_request = mock.Mock(iid=42)
        submission = pw_models.Submission.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=git_forge, merge_request=42, submission=submission
        )

        version, in_reply_to = gitlab2email._reroll(git_forge, merge_request)

        self.assertEqual(1, version)
        self.assertEqual(submission.msgid, in_reply_to)

    def test_v2_submission(self):
        """Assert the series version is +1 the previous version."""
        git_forge = models.GitForge.objects.get(pk=1)
        merge_request = mock.Mock(iid=42)
        submission = pw_models.Submission.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=git_forge,
            merge_request=42,
            submission=submission,
            series_version=1,
        )

        version, in_reply_to = gitlab2email._reroll(git_forge, merge_request)

        self.assertEqual(2, version)
        self.assertEqual(submission.msgid, in_reply_to)

    def test_v3_submission(self):
        """Assert the highest series version is selected as the reply_to."""
        git_forge = models.GitForge.objects.get(pk=1)
        merge_request = mock.Mock(iid=42)
        submission1 = pw_models.Submission.objects.get(pk=1)
        submission2 = pw_models.Submission.objects.get(pk=2)
        models.BridgedSubmission.objects.create(
            git_forge=git_forge,
            merge_request=42,
            submission=submission1,
            series_version=1,
        )
        models.BridgedSubmission.objects.create(
            git_forge=git_forge,
            merge_request=42,
            submission=submission2,
            series_version=2,
        )

        version, in_reply_to = gitlab2email._reroll(git_forge, merge_request)

        self.assertEqual(3, version)
        self.assertEqual(submission2.msgid, in_reply_to)

    def test_prior_ccs(self):
        """Assert all Ccs from prior bridged submissions are collected as Ccs."""


@mock.patch(
    "patchlab.gitlab2email.email_utils.formatdate",
    mock.Mock(return_value="Mon, 04 Nov 2019 23:00:00 -0000"),
)
class PrepareEmailsTests(BaseTestCase):
    """
    Tests for the _prepare_emails function.

    These tests are run against real test data from a GitLab server and the
    output of git-format-patch.
    """

    def setUp(self):
        self.maxDiff = None
        super().setUp()
        self.project = pw_models.Project.objects.create(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        self.forge = models.GitForge.objects.create(
            project=self.project, host="gitlab.example.com", forge_id=1
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="TEST", name="internal"
        )

    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_single_commit_mr(self, mock_make_msgid):
        """
        Assert a merge request with a single commit results in a single email.
        """
        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails))
        self.assertEqual(SINGLE_COMMIT_MR, emails[0].message().as_string())

    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_ccs(self, mock_make_msgid):
        """
        Assert a merge request with "Cc:" tags result in Ccing those users and
        the author.
        """
        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails))
        self.assertEqual(
            sorted(["user@example.com", "jcline@redhat.com"]), sorted(emails[0].cc)
        )

    @override_settings(PATCHLAB_CC_FILTER=r"@notlocaldomain.com$")
    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_ccs_not_filtered(self, mock_make_msgid):
        """
        Assert a merge request with "Cc:" tags that don't match the filter
        are ignored.
        """
        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails))
        self.assertEqual([], emails[0].cc)

    def test_no_branch(self):
        """Assert if there's no branch no emails are created."""
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(0, len(emails))

    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_no_patch_prefix(self, mock_make_msgid):
        """
        Assert if gitlab starts generating patches without [PATCH] we don't
        mangle the subject. The recorded web response has been edited to remove
        the subject prefix.
        """

        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails))
        self.assertEqual(SINGLE_COMMIT_MR, emails[0].message().as_string())

    @mock.patch("patchlab.gitlab2email.email_utils.formatdate")
    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_multi_commit_mr(self, mock_make_msgid, mock_formatdate):
        """
        Assert a merge request with multiple commits results in an email series
        with a cover letter.
        """
        mock_formatdate.return_value = "Thu, 24 Oct 2019 19:15:26 -0000"
        mock_make_msgid.side_effect = (
            "<1@localhost.localdomain>",
            "<2@localhost.localdomain>",
            "<4@localhost.localdomain>",
        )
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(3, len(emails))
        for email, expected_email in zip(emails, MULTI_COMMIT_MR):
            self.assertEqual(expected_email, email.message().as_string())

    @override_settings(PATCHLAB_MAX_EMAILS=1)
    @mock.patch("patchlab.gitlab2email.email_utils.formatdate")
    @mock.patch("patchlab.gitlab2email.email_utils.make_msgid")
    def test_huge_mr(self, mock_make_msgid, mock_formatdate):
        """Assert when the merge request has MAX_EMAILS commits we don't send them."""
        mock_formatdate.return_value = "Thu, 24 Oct 2019 19:15:26 -0000"
        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails))
        self.assertEqual(BIG_EMAIL, emails[0].message().as_string())

    def test_multiline_patch_subject(self):
        """
        Assert patches with multi-line subjects are sanitized to have single-line
        subjects. Multi-line subjects allow malicious patches to inject arbitrary
        headers into the email.
        """
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(1, len(emails[0].message()["Subject"].splitlines()))

    def test_multiline_cover_letter_subject(self):
        """
        Assert patches with multi-line subjects are sanitized to have single-line
        subjects in the cover letter.
        """
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertEqual(3, len(emails))
        for email in emails:
            self.assertEqual(1, len(email.message()["Subject"].splitlines()))

    def test_wrapped_cover_letter_body(self):
        """
        Assert cover letters that are not line-wrapped in GitLab are wrapped to
        72 characters in their email representation.
        """
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)

        emails = gitlab2email._prepare_emails(
            gitlab, self.forge, project, merge_request
        )

        self.assertTrue(len(merge_request.description.splitlines()[0]) > 72)
        for line in emails[0].message().get_payload().splitlines():
            self.assertTrue(len(line) < 73)


@mock.patch(
    "patchlab.gitlab2email.email_utils.formatdate",
    mock.Mock(return_value="Mon, 04 Nov 2019 23:00:00 -0000"),
)
class RecordBridgingTests(BaseTestCase):
    """Tests for :func:`patchlab.gitlab2email._record_bridging`."""

    def setUp(self):
        super().setUp()
        self.project = pw_models.Project.objects.create(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
            web_url="https://gitlab/root/kernel",
        )
        self.forge = models.GitForge.objects.create(
            project=self.project, host="gitlab.example.com", forge_id=1
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="ARK INTERNAL", name="internal"
        )
        self.gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )

    def test_patches_filtered_subject(self):
        """
        Assert if a patch gets filtered due to the project's subject
        filtering, we log an error so the admin knows what to do and raise an
        exception
        """
        self.project.subject_match = r"\[THIS FILTERS OUR PATCHES\]"
        self.project.save()
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )

        self.assertRaises(
            pw_models.Submission.DoesNotExist,
            gitlab2email._record_bridging,
            self.forge.project.listid,
            1,
            emails[0],
        )

    def test_multi_patch_series(self):
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )
        initial_patch_count = pw_models.Patch.objects.count()
        initial_cover_letter_count = pw_models.CoverLetter.objects.count()

        for email in emails:
            gitlab2email._record_bridging(self.forge.project.listid, 1, email)

        self.assertEqual(3, models.BridgedSubmission.objects.count())
        self.assertEqual(2, pw_models.Patch.objects.count() - initial_patch_count)
        self.assertEqual(
            1, pw_models.CoverLetter.objects.count() - initial_cover_letter_count
        )

    def test_single_patch_series(self):
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )
        initial_patch_count = pw_models.Patch.objects.count()
        initial_cover_letter_count = pw_models.CoverLetter.objects.count()

        for email in emails:
            gitlab2email._record_bridging(self.forge.project.listid, 1, email)

        self.assertEqual(1, models.BridgedSubmission.objects.count())
        self.assertEqual(1, pw_models.Patch.objects.count() - initial_patch_count)
        self.assertEqual(
            initial_cover_letter_count, pw_models.CoverLetter.objects.count()
        )

    def test_duplicate_patches(self):
        """Assert if the same emails are provided to _record_bridging it raises an exception."""
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )

        for email in emails:
            gitlab2email._record_bridging(self.forge.project.listid, 1, email)

            self.assertRaises(
                ValueError,
                gitlab2email._record_bridging,
                self.forge.project.listid,
                1,
                email,
            )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailCommentTests(BaseTestCase):
    """
    Tests for the :func:`gitlab2email.email_comment` function.
    """

    def setUp(self):
        super().setUp()
        try:
            mail.outbox.clear()
        except AttributeError:
            pass
        self.gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        self.project = pw_models.Project.objects.create(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        self.forge = models.GitForge.objects.create(
            project=self.project, host="gitlab", forge_id=42
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="TEST", name="internal"
        )
        with open(os.path.join(FIXTURES, "inline_code_comment.json")) as fd:
            self.inline_code_comment_payload = json.load(fd)
        with open(os.path.join(FIXTURES, "comment_on_commit.json")) as fd:
            self.comment_on_commit_payload = json.load(fd)
        with open(os.path.join(FIXTURES, "comment_on_mr.json")) as fd:
            self.comment_on_mr_payload = json.load(fd)

    def test_comment_no_bridged_email(self):
        """Assert if no merge request is recorded as bridged, we email nothing."""
        gitlab2email.email_comment(
            self.gitlab,
            self.forge.forge_id,
            self.comment_on_mr_payload["user"],
            self.comment_on_mr_payload["object_attributes"],
            1,
        )
        self.assertEqual(0, len(mail.outbox))

    def test_comment_on_mr_email(self):
        """Assert comments bridged MRs are emailed."""
        submission = pw_models.Submission.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=self.forge, merge_request=42, submission=submission
        )
        expected_body = (
            "From: Administrator on gitlab\n"
            "https://gitlab/root/patchlab_test/merge_requests/1#note_2\n\n"
            "Not great, not terrible.\n"
        )

        gitlab2email.email_comment(
            self.gitlab,
            self.forge.forge_id,
            self.comment_on_mr_payload["user"],
            self.comment_on_mr_payload["object_attributes"],
            42,
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(expected_body, mail.outbox[0].body)

    def test_comment_on_commit_email(self):
        """Assert comments bridged MRs are emailed."""
        submission = pw_models.Submission.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=self.forge,
            merge_request=42,
            submission=submission,
            commit="2311157d92dc85e012342cd07c503ee397af2f1e",
        )
        expected_body = (
            "From: Administrator on gitlab\n"
            "https://gitlab/root/patchlab_test/commit/"
            "2311157d92dc85e012342cd07c503ee397af2f1e#note_4\n\n"
            "Here's a comment on a commit\n"
        )

        gitlab2email.email_comment(
            self.gitlab,
            self.forge.forge_id,
            self.comment_on_commit_payload["user"],
            self.comment_on_commit_payload["object_attributes"],
            42,
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(expected_body, mail.outbox[0].body)

    def test_inline_code_comment_email(self):
        """Assert comments bridged MRs are emailed."""
        submission = pw_models.Submission.objects.first()
        models.BridgedSubmission.objects.create(
            git_forge=self.forge, merge_request=42, submission=submission
        )
        expected_body = (
            "From: Administrator on gitlab\n"
            "https://gitlab/root/patchlab_test/merge_requests/1#note_3\n\n"
            "This change in particular, I don't like it.\n"
        )

        gitlab2email.email_comment(
            self.gitlab,
            self.forge.forge_id,
            self.inline_code_comment_payload["user"],
            self.inline_code_comment_payload["object_attributes"],
            42,
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(expected_body, mail.outbox[0].body)
