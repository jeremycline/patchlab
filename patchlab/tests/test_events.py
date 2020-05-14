# SPDX-License-Identifier: GPL-2.0-or-later
from unittest import mock

from django.test import override_settings

from patchlab import events
from . import BaseTestCase


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CommentEventsTests(BaseTestCase):
    def test_ignore_emails_with_header(self):
        """Assert emails generated from email_comment are ignored"""
        headers = (
            'Content-Type: text/plain; charset="utf-8"\n'
            "MIME-Version: 1.0\n"
            "Content-Transfer-Encoding: 7bit\n"
            "Subject: Re: [TEST PATCH] Bring balance to the equals signs\n"
            'From: Email Bridge on behalf of ["author"] <bridge@example.com>\n'
            "To: kernel@lists.fedoraproject.org\n"
            "Reply-To: kernel@lists.fedoraproject.org\n"
            "Date: Thu, 14 May 2020 19:10:37 -0000\n"
            "Message-ID: <158948343717.47562.17314000735326197482@patchwork>\n"
            "In-Reply-To: <4@localhost.localdomain>\n"
            "X-Patchlab-Comment: https://gitlab/root/patchlab_test/merge_requests/1#note_3\n"
        )
        mock_comment = mock.Mock(headers=headers)

        with mock.patch("patchlab.events._log") as log:
            events.comment_event_handler(None, **{"instance": mock_comment})
            log.info.assert_called_once_with(
                "Ignoring instance %d as it originated from the bridge.",
                mock_comment.id,
            )
