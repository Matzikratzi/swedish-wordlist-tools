from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools.ocr_batch_progress_cache import BatchProgressStore
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_review_batch_defects_html import (
    defect_url,
    editor_argv,
    parse_pages,
    scan_context,
)


class BatchDefectReviewTests(unittest.TestCase):
    def test_parse_pages_accepts_ranges_and_deduplicates(self) -> None:
        self.assertEqual(parse_pages("7-9,11,9,13-14"), [7, 8, 9, 11, 13, 14])

    def test_parse_pages_rejects_descending_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_pages("9-7")

    def test_scan_context_keeps_only_settled_pixel_defects(self) -> None:
        context = {"page_number": 7, "positions": [(0, 0), (0, 1), (1, 0)]}
        states = {
            (0, 0): {"column": 0, "row": 0, "source_pixels": 100, "covered_pixels": 100, "text": "a"},
            (0, 1): {"column": 0, "row": 1, "source_pixels": 90, "covered_pixels": 83, "text": "b"},
            (1, 0): {"column": 1, "row": 0, "source_pixels": 80, "covered_pixels": 80, "text": "c"},
        }

        with patch(
            "swedish_wordlist_tools.ocr_review_batch_defects_html._load_review_state_for_audit",
            side_effect=lambda _context, position, _models: states[position],
        ):
            report = scan_context(context, [])

        self.assertFalse(report["complete_scan"])
        self.assertEqual(report["rows_scanned"], 3)
        self.assertEqual(report["rows_exact"], 2)
        self.assertEqual(report["unknown_pixels"], 7)
        self.assertEqual(len(report["defects"]), 1)
        self.assertEqual(report["defects"][0]["column"], 0)
        self.assertEqual(report["defects"][0]["row"], 1)

    def test_scan_context_can_stop_at_first_pixel_defect(self) -> None:
        context = {"page_number": 7, "positions": [(0, 0), (0, 1), (1, 0), (1, 1)]}
        states = {
            (0, 0): {"column": 0, "row": 0, "source_pixels": 100, "covered_pixels": 100, "text": "a"},
            (0, 1): {"column": 0, "row": 1, "source_pixels": 90, "covered_pixels": 83, "text": "b"},
            (1, 0): {"column": 1, "row": 0, "source_pixels": 80, "covered_pixels": 80, "text": "c"},
            (1, 1): {"column": 1, "row": 1, "source_pixels": 70, "covered_pixels": 70, "text": "d"},
        }
        visited = []

        def load(_context, position, _models):
            visited.append(position)
            return states[position]

        with patch(
            "swedish_wordlist_tools.ocr_review_batch_defects_html._load_review_state_for_audit",
            side_effect=load,
        ):
            report = scan_context(context, [], stop_after_first_defect=True)

        self.assertEqual(visited, [(0, 0), (0, 1)])
        self.assertFalse(report["complete_scan"])
        self.assertEqual(report["rows_scanned"], 2)
        self.assertEqual(report["rows_exact"], 1)
        self.assertEqual(len(report["defects"]), 1)
        self.assertEqual(report["defects"][0]["row"], 1)

    def test_scan_context_resumes_at_saved_index(self) -> None:
        context = {"page_number": 7, "positions": [(0, 0), (0, 1), (1, 0), (1, 1)]}
        states = {
            (1, 0): {"column": 1, "row": 0, "source_pixels": 80, "covered_pixels": 80, "text": "c"},
            (1, 1): {"column": 1, "row": 1, "source_pixels": 70, "covered_pixels": 65, "text": "d"},
        }
        visited = []
        saved = []

        def load(_context, position, _models):
            visited.append(position)
            return states[position]

        with patch(
            "swedish_wordlist_tools.ocr_review_batch_defects_html._load_review_state_for_audit",
            side_effect=load,
        ):
            report = scan_context(
                context,
                [],
                start_index=2,
                stop_after_first_defect=True,
                exact_callback=lambda next_index, position: saved.append((next_index, position)),
            )

        self.assertEqual(visited, [(1, 0), (1, 1)])
        self.assertEqual(saved, [(3, (1, 0))])
        self.assertEqual(report["rows_scanned"], 2)
        self.assertEqual(report["start_index"], 2)

    def test_progress_cache_survives_facit_additions_and_rewinds_one_row(self) -> None:
        old = GlyphModel("a", "roman", frozenset({(0, 0)}))
        added = GlyphModel("b", "roman", frozenset({(0, 0), (1, 0)}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            store = BatchProgressStore(path)
            store.save_frontier(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                next_index=6,
                models=[old],
            )
            reopened = BatchProgressStore(path)
            start, complete = reopened.resume_index(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                models=[old, added],
            )
            self.assertEqual(start, 5)
            self.assertFalse(complete)

    def test_progress_cache_invalidates_if_old_facit_model_disappears(self) -> None:
        old = GlyphModel("a", "roman", frozenset({(0, 0)}))
        replacement = GlyphModel("a", "italic", frozenset({(0, 0)}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            store = BatchProgressStore(path)
            store.save_frontier(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                next_index=6,
                models=[old],
            )
            start, complete = store.resume_index(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                models=[replacement],
            )
            self.assertEqual(start, 0)
            self.assertFalse(complete)

    def test_progress_cache_can_skip_complete_page(self) -> None:
        model = GlyphModel("a", "roman", frozenset({(0, 0)}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            store = BatchProgressStore(path)
            store.save_frontier(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                next_index=10,
                models=[model],
                complete=True,
            )
            start, complete = store.resume_index(
                page=7,
                threshold=210,
                source_digest="source",
                row_count=10,
                models=[model],
            )
            self.assertEqual(start, 10)
            self.assertTrue(complete)

    def test_defect_url_opens_existing_editor_in_defect_mode(self) -> None:
        url = defect_url("127.0.0.1", 8766, (2, 17))
        self.assertTrue(url.startswith("http://127.0.0.1:8766/"))
        self.assertIn("column=2", url)
        self.assertIn("row=17", url)
        self.assertIn("mode=defects", url)

    def test_editor_argv_uses_normal_boundary_editor_arguments(self) -> None:
        argv = editor_argv(
            Path("/tmp/saol.jsonl"),
            page=8,
            position=(1, 23),
            threshold=210,
            facit=Path("glyphs/facit.json"),
            host="127.0.0.1",
            port=8766,
            no_browser=True,
        )
        self.assertEqual(argv[0], "ocr_review_five_rows_glyphs_boundary_html")
        self.assertIn("--page", argv)
        self.assertIn("8", argv)
        self.assertIn("--column", argv)
        self.assertIn("1", argv)
        self.assertIn("--row", argv)
        self.assertIn("23", argv)
        self.assertIn("--no-browser", argv)


if __name__ == "__main__":
    unittest.main()
