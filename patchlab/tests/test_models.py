import email

from patchwork import models as pw_models
from patchwork.parser import parse_mail

from patchlab import models
from . import SINGLE_COMMIT_MR, BaseTestCase


class BranchTests(BaseTestCase):
    def setUp(self):
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
        parse_mail(
            email.message_from_string(SINGLE_COMMIT_MR),
            "kernel.lists.fedoraproject.org",
        )
        models.Branch.objects.create(
            git_forge=self.forge,
            name="master",
            subject_prefix="TEST",
            subject_match=r"^.*\[.*TEST.*\].*$",
        )

    def test_no_matches(self):
        """Assert that when the subject_match doesn't match, a ValueError occurs."""
        branch = self.forge.branches.first()
        branch.subject_match = r"^Does Not Match$"
        branch.save()
        submission = pw_models.Submission.objects.first()

        self.assertRaises(ValueError, self.forge.branch, submission)

    def test_match(self):
        """Assert the forge is returned when its subject match matches."""
        submission = pw_models.Submission.objects.first()

        self.assertEqual("master", self.forge.branch(submission))
