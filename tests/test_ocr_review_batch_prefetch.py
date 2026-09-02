from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools.ocr_review_batch_prefetch import BatchPrefetcher


class BatchPrefetchTests(unittest.TestCase):
    def test_prefetch_moves_to_later_pages_and_stops_on_unresolved_defect(self) -> None:
        reports = {
            9: {"defects": [], "cached_complete": False},
            10: {"defects": [{"column": 1, "row": 7, "unknown_pixels": 3}]},
        }
        visited = []
        messages = []

        def fake_scan_page(_jsonl, page, _models, **_kwargs):
            visited.append(page)
            return reports[page]

        def printer(*args, **_kwargs):
            messages.append(" ".join(str(arg) for arg in args))

        prefetcher = BatchPrefetcher(
            jsonl=Path("/tmp/saol.jsonl"),
            pages=[9, 10, 11],
            threshold=210,
            facit=Path("/tmp/facit.json"),
            progress_store=object(),
            printer=printer,
        )

        with patch(
            "swedish_wordlist_tools.ocr_review_batch_prefetch.load_facit",
            return_value=[],
        ), patch(
            "swedish_wordlist_tools.ocr_review_batch_prefetch.scan_page",
            side_effect=fake_scan_page,
        ), patch.object(prefetcher, "_wait_for_facit_change", return_value=False):
            prefetcher._run()

        self.assertEqual(visited, [9, 10])
        self.assertTrue(any("page=9: EXAKT" in message for message in messages))
        self.assertTrue(any("page=10: väntar" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
