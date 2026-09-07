import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_sequential_page_review import (
    _analyse_paths,
    _debug_has_jsonl_anchor,
    _default_workers,
)


class SequentialPageReviewParallelTest(unittest.TestCase):
    def test_prefilter_skips_unanchored_debug_boxes_before_expensive_matching(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            anchored = root / "anchored.json"
            unanchored = root / "unanchored.json"
            anchored.write_text(
                json.dumps({"jsonl_hint": {"text": "s. +en"}}),
                encoding="utf-8",
            )
            unanchored.write_text(
                json.dumps({"jsonl_hint": None}),
                encoding="utf-8",
            )

            self.assertTrue(_debug_has_jsonl_anchor(anchored))
            self.assertFalse(_debug_has_jsonl_anchor(unanchored))

    def test_empty_parallel_analysis_needs_no_facit_or_workers(self):
        self.assertEqual(_analyse_paths([], Path("missing-facit.json"), 8), [])

    def test_default_worker_count_is_bounded(self):
        self.assertGreaterEqual(_default_workers(), 1)
        self.assertLessEqual(_default_workers(), 8)


if __name__ == "__main__":
    unittest.main()
