from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_page_glyph_audit import (
    _load_review_state_for_audit,
    cluster_records,
    is_cluster_label,
)


class PageGlyphAuditTest(unittest.TestCase):
    def test_single_character_labels_are_not_clusters(self):
        self.assertFalse(is_cluster_label("a"))
        self.assertFalse(is_cluster_label("·"))
        self.assertFalse(is_cluster_label("¹"))

    def test_multi_character_labels_are_clusters(self):
        self.assertTrue(is_cluster_label("tt"))
        self.assertTrue(is_cluster_label("rn"))
        self.assertTrue(is_cluster_label("el."))

    def test_cluster_records_only_returns_multi_character_matches(self):
        state = {
            "matches": [
                Match("a", "roman", 2, 8, frozenset({(2, 7), (2, 8)}), 2, 3),
                Match("tt", "roman", 7, 8, frozenset({(7, 6), (8, 6), (7, 8), (8, 8)}), 4, 1),
            ]
        }
        records = cluster_records(state)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["label"], "tt")
        self.assertEqual(records[0]["x0"], 7)
        self.assertEqual(records[0]["x1"], 8)
        self.assertEqual(records[0]["pixels"], 4)
        self.assertEqual(records[0]["sources"], 1)

    def test_row_loader_suppresses_boundary_diagnostics_on_both_streams(self):
        expected = {"column": 0, "row": 0}

        def noisy_loader(context, position, models):
            print("review: stdout boundary diagnostic")
            print("review: stderr boundary diagnostic", file=__import__("sys").stderr)
            return expected

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with patch(
            "swedish_wordlist_tools.ocr_page_glyph_audit.load_review_state_with_cached_boundaries",
            side_effect=noisy_loader,
        ):
            with redirect_stdout(captured_out), redirect_stderr(captured_err):
                actual = _load_review_state_for_audit({}, (0, 0), [])
                print("normal stdout survives")
                print("progress survives", file=__import__("sys").stderr)

        self.assertIs(actual, expected)
        self.assertNotIn("boundary diagnostic", captured_out.getvalue())
        self.assertNotIn("boundary diagnostic", captured_err.getvalue())
        self.assertIn("normal stdout survives", captured_out.getvalue())
        self.assertIn("progress survives", captured_err.getvalue())

    def test_row_loader_repeats_until_new_boundary_has_settled(self):
        states = [
            {
                "column": 0,
                "row": 46,
                "covered_pixels": 374,
                "source_pixels": 384,
                "row_boundary_correction_learned": {"corrected_boundary": 914},
            },
            {
                "column": 0,
                "row": 46,
                "covered_pixels": 374,
                "source_pixels": 374,
            },
        ]
        with patch(
            "swedish_wordlist_tools.ocr_page_glyph_audit.load_review_state_with_cached_boundaries",
            side_effect=states,
        ) as loader:
            state = _load_review_state_for_audit({}, (0, 46), [])

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(state["covered_pixels"], 374)
        self.assertEqual(state["source_pixels"], 374)
        self.assertNotIn("row_boundary_correction_learned", state)


if __name__ == "__main__":
    unittest.main()
