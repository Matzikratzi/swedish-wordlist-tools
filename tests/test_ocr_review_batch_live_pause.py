from __future__ import annotations

import threading
import unittest

from swedish_wordlist_tools.ocr_review_batch_live_html import (
    _FinishAwareServer,
    _add_finish_button,
    _plain_editor_url,
)


class PausedLiveBatchTests(unittest.TestCase):
    def test_finish_button_is_added_to_editor_html(self) -> None:
        html = '<html><body><p>editor</p></body></html>'
        result = _add_finish_button(html, 'http://127.0.0.1:8767/finish')
        self.assertIn('Klar med editeringen – fortsätt', result)
        self.assertIn('http://127.0.0.1:8767/finish', result)
        self.assertLess(result.index('Klar med editeringen'), result.index('<p>editor</p>'))

    def test_plain_editor_url_does_not_enable_defect_scan(self) -> None:
        url = _plain_editor_url('127.0.0.1', 8766, (2, 41))
        self.assertEqual(url, 'http://127.0.0.1:8766/?column=2&row=41&mode=all')
        self.assertNotIn('mode=defects', url)
        self.assertNotIn('anchor_', url)

    def test_finish_aware_server_stops_only_after_finish_event(self) -> None:
        event = threading.Event()
        _FinishAwareServer.finish_event = event
        server = object.__new__(_FinishAwareServer)
        server.service_actions()
        event.set()
        with self.assertRaises(KeyboardInterrupt):
            server.service_actions()
        _FinishAwareServer.finish_event = None


if __name__ == '__main__':
    unittest.main()
