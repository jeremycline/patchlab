from unittest import mock

from django.test import override_settings
from patchwork import models as pw_models
import gitlab as gitlab_module

from patchlab import gitlab2email, models
from . import BIG_EMAIL, SINGLE_COMMIT_MR, MULTI_COMMIT_MR, BaseTestCase


class EmailMergeRequestTests(BaseTestCase):
    @mock.patch("patchlab.gitlab2email._log")
    def test_no_forge(self, mock_log):
        """Assert when no forge in the database matches the project id and host nothing happens."""
        gitlab = mock.Mock(spec=gitlab_module.Gitlab)
        gitlab.url = "https://example.com"

        gitlab2email.email_merge_request(gitlab, 1, 1)

        mock_log.error.assert_called_once_with(
            "Request to bridge merge id %d from project id %d on %s cannot "
            "be handled as no git forge is configured in Patchlab's database.",
            1,
            1,
            "example.com",
        )


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
            project=self.project, host="gitlab.example.com", forge_id=1,
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="TEST", name="internal",
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


@mock.patch(
    "patchlab.gitlab2email.email_utils.formatdate",
    mock.Mock(return_value="Mon, 04 Nov 2019 23:00:00 -0000"),
)
class RecordBridgingTests(BaseTestCase):
    """Tests for :func:`patchlab.gitlab2email._record_bridging`."""

    def setUp(self):
        super().setUp()
        pw_models.State(ordering=0, name="test").save()
        self.project = pw_models.Project.objects.create(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
            web_url="https://gitlab/root/kernel",
        )
        self.forge = models.GitForge.objects.create(
            project=self.project, host="gitlab.example.com", forge_id=1,
        )
        self.branch = models.Branch.objects.create(
            git_forge=self.forge, subject_prefix="ARK INTERNAL", name="internal",
        )
        self.gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )

    def test_multi_patch_series(self):
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )

        gitlab2email._record_bridging(self.forge.project.listid, 1, emails)

        self.assertEqual(3, models.BridgedSubmission.objects.count())
        self.assertEqual(2, pw_models.Patch.objects.count())
        self.assertEqual(1, pw_models.CoverLetter.objects.count())

    def test_single_patch_series(self):
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )

        gitlab2email._record_bridging(self.forge.project.listid, 1, emails)

        self.assertEqual(1, models.BridgedSubmission.objects.count())
        self.assertEqual(1, pw_models.Patch.objects.count())

    def test_duplicate_patches(self):
        """Assert if the same emails are provided to _record_bridging it raises an exception."""
        project = self.gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = gitlab2email._prepare_emails(
            self.gitlab, self.forge, self.project, merge_request
        )

        gitlab2email._record_bridging(self.forge.project.listid, 1, emails)
        self.assertRaises(
            ValueError,
            gitlab2email._record_bridging,
            self.forge.project.listid,
            1,
            emails,
        )
