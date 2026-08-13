from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_adjective_structural_coverage import build_summary


class AnalyzeAdjectiveStructuralCoverageTests(unittest.TestCase):
    def test_separates_shared_metadata_variants_and_inflection_mechanics(self) -> None:
        rows = (
            {"rule": "shared_positive_atoms"},
            {"rule": "structural_labelled_positive_slots"},
            {"rule": "structural_labelled_comparison_slots"},
            {"rule": "structural_usage_restrictions"},
            {"rule": "structural_parallel_explicit_variant"},
            {"rule": "structural_full_labelled_slots"},
            {"rule": "lemma_only_no_inflection_text"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adj.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            summary = build_summary(path)

        self.assertEqual(1, summary["shared_direct_records"])
        self.assertEqual(2, summary["shared_backed_records"])
        self.assertEqual(3, summary["shared_records"])
        self.assertEqual(1, summary["metadata_records"])
        self.assertEqual(1, summary["variant_relation_records"])
        self.assertEqual(1, summary["structural_records"])
        self.assertEqual(6, summary["clean_room_records"])
        self.assertEqual(1, summary["no_inflection_text_records"])
        self.assertEqual(0, summary["legacy_records"])


if __name__ == "__main__":
    unittest.main()
