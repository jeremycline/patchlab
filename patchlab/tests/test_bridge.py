from unittest import TestCase, mock

from .. import bridge


class PrExistsTests(TestCase):
    @mock.patch("patchlab.bridge.gitlab")
    def test_pr_exists(self, mock_gitlab):
        self.assertTrue(bridge.pr_exists(1, "email/series-1"))
