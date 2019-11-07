from unittest import mock
import os

from django.test import override_settings, TestCase as DjangoTestCase
from patchwork import models as pw_models
import vcr
import gitlab as gitlab_module

from patchlab import tasks, models
from ..tests import FIXTURES

import urllib

single_commit_email = """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: [TEST PATCH] Bring balance to the equals signs
From: Patchwork <patchwork@patchwork.example.com>
To: kernel@lists.fedoraproject.org
Cc: Administrator <admin@example.com>
Reply-To: kernel@lists.fedoraproject.org
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <4@localhost.localdomain>
X-Patchlab-Patch-Author: Jeremy Cline <jcline@redhat.com>
X-Patchlab-Merge-Request: https://gitlab/root/kernel/merge_requests/1
X-Patchlab-Commit: a958a0dff5e3c433eb99bc5f18cbcfad77433b0d

This is a silly change so I can write a test.

Signed-off-by: Jeremy Cline <jcline@redhat.com>
---
 README | 1 +
 1 file changed, 1 insertion(+)

diff --git a/README b/README
index 669ac7c32292..a0cc9c082916 100644
--- a/README
+++ b/README
@@ -1,3 +1,4 @@
+============
 Linux kernel
 ============
 
-- 
2.22.0

"""

multi_commit_emails = [
    """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: [TEST PATCH 0/2] Update the README
From: Patchwork <patchwork@patchwork.example.com>
To: kernel@lists.fedoraproject.org
Cc: Administrator <admin@example.com>
Reply-To: kernel@lists.fedoraproject.org
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <1@localhost.localdomain>
X-Patchlab-Merge-Request: https://gitlab/root/kernel/merge_requests/2

Update the README to make me want to read it more.""",
    """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: [TEST PATCH 1/2] Bring balance to the equals signs
From: Patchwork <patchwork@patchwork.example.com>
To: kernel@lists.fedoraproject.org
Cc: Administrator <admin@example.com>
Reply-To: kernel@lists.fedoraproject.org
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <2@localhost.localdomain>
X-Patchlab-Patch-Author: Jeremy Cline <jcline@redhat.com>
X-Patchlab-Merge-Request: https://gitlab/root/kernel/merge_requests/2
X-Patchlab-Commit: 5c9b066a8bc9eed0e8d7ccd392bc8f77c42532f0

This is a silly change so I can write a test.

Signed-off-by: Jeremy Cline <jcline@redhat.com>
---
 README | 1 +
 1 file changed, 1 insertion(+)

diff --git a/README b/README
index 669ac7c32292..a0cc9c082916 100644
--- a/README
+++ b/README
@@ -1,3 +1,4 @@
+============
 Linux kernel
 ============
 
-- 
2.22.0

""",
    """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: [TEST PATCH 2/2] Convert the README to restructured text
From: Patchwork <patchwork@patchwork.example.com>
To: kernel@lists.fedoraproject.org
Cc: Administrator <admin@example.com>
Reply-To: kernel@lists.fedoraproject.org
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <4@localhost.localdomain>
X-Patchlab-Patch-Author: Jeremy Cline <jcline@redhat.com>
X-Patchlab-Merge-Request: https://gitlab/root/kernel/merge_requests/2
X-Patchlab-Commit: c321c86ee75491f4bc0b0b0e368f71eff88fa91c

Make the README more readable.

Signed-off-by: Jeremy Cline <jcline@redhat.com>
---
 README => README.rst | 0
 1 file changed, 0 insertions(+), 0 deletions(-)
 rename README => README.rst (100%)

diff --git a/README b/README.rst
similarity index 100%
rename from README
rename to README.rst
-- 
2.22.0

""",
]

big_email = """Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: [TEST PATCH 0/2] Update the README
From: Patchwork <patchwork@patchwork.example.com>
To: kernel@lists.fedoraproject.org
Cc: Administrator <admin@example.com>
Reply-To: kernel@lists.fedoraproject.org
Date: Mon, 04 Nov 2019 23:00:00 -0000
Message-ID: <4@localhost.localdomain>
X-Patchlab-Merge-Request: https://gitlab/root/kernel/merge_requests/2

Update the README to make me want to read it more.

Note:

The patch series is too large to sent by email.

Reviewing locally, set up your repository to fetch from the GitLab remote:

  $ git remote add gitlab https://gitlab/root/kernel.git
  $ git config remote.gitlab.fetch '+refs/merge-requests/*:refs/remotes/origin/merge-requests/*'
  $ git fetch gitlab

Finally, check out the merge request:

  $ git checkout merge-requests/2

It is also possible to review the merge request on GitLab at:
    https://gitlab/root/kernel/merge_requests/2
"""


@mock.patch(
    "patchlab.tasks.email_utils.formatdate",
    mock.Mock(return_value="Mon, 04 Nov 2019 23:00:00 -0000"),
)
class PrepareEmailsTests(DjangoTestCase):
    """
    Tests for the _prepare_emails function.

    These tests are run against real test data from a GitLab server and the
    output of git-format-patch.
    """

    def setUp(self):
        self.maxDiff = None
        my_vcr = vcr.VCR(
            cassette_library_dir=os.path.join(FIXTURES, "VCR/"), record_mode="once"
        )
        self.vcr = my_vcr.use_cassette(self.id())
        self.vcr.__enter__()
        self.addCleanup(self.vcr.__exit__, None, None, None)

        self.project = pw_models.Project(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        self.forge = models.GitForge(
            project=self.project,
            host="gitlab.example.com",
            forge_id=1,
            subject_prefix="TEST PATCH",
        )

    @mock.patch("patchlab.tasks.email_utils.make_msgid")
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

        emails = tasks._prepare_emails(gitlab, self.forge, project, merge_request)

        self.assertEqual(1, len(emails))
        self.assertEqual(single_commit_email, emails[0].message().as_string())

    @mock.patch("patchlab.tasks.email_utils.make_msgid")
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

        emails = tasks._prepare_emails(gitlab, self.forge, project, merge_request)

        self.assertEqual(1, len(emails))
        self.assertEqual(single_commit_email, emails[0].message().as_string())

    @mock.patch("patchlab.tasks.email_utils.formatdate")
    @mock.patch("patchlab.tasks.email_utils.make_msgid")
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

        emails = tasks._prepare_emails(gitlab, self.forge, project, merge_request)

        self.assertEqual(3, len(emails))
        for email, expected_email in zip(emails, multi_commit_emails):
            self.assertEqual(expected_email, email.message().as_string())

    @override_settings(PATCHLAB_MAX_EMAILS=1)
    @mock.patch("patchlab.tasks.email_utils.formatdate")
    @mock.patch("patchlab.tasks.email_utils.make_msgid")
    def test_huge_mr(self, mock_make_msgid, mock_formatdate):
        """Assert when the merge request has MAX_EMAILS commits we don't send them."""
        mock_formatdate.return_value = "Thu, 24 Oct 2019 19:15:26 -0000"
        mock_make_msgid.return_value = "<4@localhost.localdomain>"
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)

        emails = tasks._prepare_emails(gitlab, self.forge, project, merge_request)

        self.assertEqual(1, len(emails))
        self.assertEqual(big_email, emails[0].message().as_string())


@mock.patch(
    "patchlab.tasks.email_utils.formatdate",
    mock.Mock(return_value="Mon, 04 Nov 2019 23:00:00 -0000"),
)
class RecordBridgingTests(DjangoTestCase):
    """Tests for :func:`patchlab.tasks._record_bridging`."""

    def setUp(self):
        self.maxDiff = None
        my_vcr = vcr.VCR(
            cassette_library_dir=os.path.join(FIXTURES, "VCR/"), record_mode="once"
        )
        self.vcr = my_vcr.use_cassette(self.id())
        self.vcr.__enter__()
        self.addCleanup(self.vcr.__exit__, None, None, None)
        super().setUp()

    def test_multi_patch_series(self):
        project = pw_models.Project(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        project.save()
        pw_models.State(ordering=0, name="test").save()
        forge = models.GitForge(
            project=project,
            host="gitlab.example.com",
            forge_id=1,
            subject_prefix="ARK INTERNAL PATCH",
        )
        forge.save()
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(2)
        emails = tasks._prepare_emails(gitlab, forge, project, merge_request)

        tasks._record_bridging(forge.project.listid, 1, emails)

        self.assertEqual(3, models.BridgedSubmission.objects.count())
        self.assertEqual(2, pw_models.Patch.objects.count())
        self.assertEqual(1, pw_models.CoverLetter.objects.count())

    def test_single_patch_series(self):
        project = pw_models.Project(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        project.save()
        pw_models.State(ordering=0, name="test").save()
        forge = models.GitForge(
            project=project,
            host="gitlab.example.com",
            forge_id=1,
            subject_prefix="ARK INTERNAL PATCH",
        )
        forge.save()
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = tasks._prepare_emails(gitlab, forge, project, merge_request)

        tasks._record_bridging(forge.project.listid, 1, emails)

        self.assertEqual(1, models.BridgedSubmission.objects.count())
        self.assertEqual(1, pw_models.Patch.objects.count())

    def test_duplicate_patches(self):
        """Assert if the same emails are provided to _record_bridging it raises an exception."""
        project = pw_models.Project(
            linkname="ark",
            name="ARK",
            listid="kernel.lists.fedoraproject.org",
            listemail="kernel@lists.fedoraproject.org",
        )
        project.save()
        pw_models.State(ordering=0, name="test").save()
        forge = models.GitForge(
            project=project,
            host="gitlab.example.com",
            forge_id=1,
            subject_prefix="ARK INTERNAL PATCH",
        )
        forge.save()
        gitlab = gitlab_module.Gitlab(
            "https://gitlab", private_token="iaxMadvFyRCFRFH1CkW6", ssl_verify=False
        )
        project = gitlab.projects.get(1)
        merge_request = project.mergerequests.get(1)
        emails = tasks._prepare_emails(gitlab, forge, project, merge_request)

        tasks._record_bridging(forge.project.listid, 1, emails)
        self.assertRaises(
            ValueError, tasks._record_bridging, forge.project.listid, 1, emails
        )
