from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools.ocr_collect_defect_manifest import write_manifest
from swedish_wordlist_tools.ocr_review_defect_manifest import first_unresolved, load_manifest


class DefectManifestTests(unittest.TestCase):
    def test_roundtrip_preserves_page_column_row(self) -> None:
        records = [
            {"page": 21, "column": 0, "row": 7, "unknown_pixels": 3, "text": "abc"},
            {"page": 22, "column": 2, "row": 19, "unknown_pixels": 8, "text": "def"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "defects.jsonl"
            write_manifest(path, records)
            self.assertEqual(load_manifest(path), records)

    def test_first_unresolved_skips_rows_fixed_by_new_facit(self) -> None:
        records = [
            {"page": 21, "column": 0, "row": 7},
            {"page": 21, "column": 0, "row": 8},
        ]
        context = {"positions": [(0, 7), (0, 8)]}
        states = [
            {"source_pixels": 10, "covered_pixels": 10},
            {"source_pixels": 12, "covered_pixels": 9},
        ]
        with patch(
            "swedish_wordlist_tools.ocr_review_defect_manifest.build_page_context",
            return_value=context,
        ), patch(
            "swedish_wordlist_tools.ocr_review_defect_manifest._load_review_state_for_audit",
            side_effect=states,
        ):
            found = first_unresolved(Path("x.jsonl"), records, [], threshold=210)
        self.assertIsNotNone(found)
        index, record, unknown = found
        self.assertEqual(index, 1)
        self.assertEqual((record["page"], record["column"], record["row"]), (21, 0, 8))
        self.assertEqual(unknown, 3)


if __name__ == "__main__":
    unittest.main()
