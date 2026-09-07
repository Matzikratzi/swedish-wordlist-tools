from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_recent_glyph_rows import editor_command, recent_source_rows


class RecentGlyphRowsTests(unittest.TestCase):
    def test_recent_rows_are_newest_first_and_deduplicated(self) -> None:
        data = {
            "glyphs": [
                {"label": "a", "style": "roman", "sources": [{"page": 1, "column": 0, "row": 1}]},
                {"label": "b", "style": "italic", "sources": [{"page": 2, "column": 1, "row": 3}]},
                {"label": "c", "style": "roman", "sources": [{"page": 2, "column": 1, "row": 3}]},
                {"label": "d", "style": "bold", "sources": [{"page": 3, "column": 2, "row": 4}]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facit.json"
            path.write_text(json.dumps(data))
            rows = recent_source_rows(path, 20)

        self.assertEqual(
            [(r["page"], r["column"], r["row"]) for r in rows],
            [(3, 2, 4), (2, 1, 3), (1, 0, 1)],
        )
        self.assertEqual(rows[1]["glyphs"], [("c", "roman"), ("b", "italic")])

    def test_limit_counts_unique_rows_not_glyphs(self) -> None:
        data = {
            "glyphs": [
                {"label": "a", "sources": [{"page": 1, "column": 0, "row": 1}]},
                {"label": "b", "sources": [{"page": 2, "column": 0, "row": 2}]},
                {"label": "c", "sources": [{"page": 3, "column": 0, "row": 3}]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facit.json"
            path.write_text(json.dumps(data))
            rows = recent_source_rows(path, 2)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["page"], 3)
        self.assertEqual(rows[1]["page"], 2)

    def test_editor_command_targets_ordinary_boundary_editor(self) -> None:
        command = editor_command(
            Path("/tmp/saol.jsonl"),
            {"page": 8, "column": 2, "row": 29},
            port=8766,
        )
        self.assertIn("ocr_review_five_rows_glyphs_boundary_html", command)
        self.assertIn("--page 8", command)
        self.assertIn("--column 2", command)
        self.assertIn("--row 29", command)
        self.assertIn("--port 8766", command)


if __name__ == "__main__":
    unittest.main()
