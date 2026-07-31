from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_unresolved import (
    export_unresolved,
    filter_unresolved,
    selectors,
    solved_compound_selectors,
)


class ExportUnresolvedTests(unittest.TestCase):
    def test_subtracts_only_solved_compounds_from_baseline(self) -> None:
        baseline = selectors(
            [
                {"record_id": "1", "lemma": "ambiguous"},
                {"record_id": "2", "lemma": "olöstord"},
                {"record_id": "3", "lemma": "löstord"},
            ]
        )
        compounds = solved_compound_selectors(
            [
                {
                    "record_id": "2",
                    "head_match_reason": "multiple_heads_same_upos",
                },
                {
                    "record_id": "3",
                    "head_match_reason": "unique_head_same_upos",
                },
            ]
        )
        original = [
            {"id": "1", "normaliserat_ord": "ambiguous"},
            {"id": "2", "normaliserat_ord": "olöstord"},
            {"id": "3", "normaliserat_ord": "löstord"},
            {"id": "4", "normaliserat_ord": "direktlöst"},
        ]

        rows = filter_unresolved(original, baseline, compounds)

        self.assertEqual(["1", "2"], [row["id"] for row in rows])

    def test_keeps_original_saol_rows_unchanged(self) -> None:
        original = [
            {"id": "1", "normaliserat_ord": "ett", "nested": {"x": 1}},
            {"id": "2", "normaliserat_ord": "två", "nested": {"x": 2}},
        ]
        baseline = selectors([{"record_id": "2"}])

        rows = filter_unresolved(original, baseline, set())

        self.assertEqual([original[1]], rows)

    def test_writes_jsonl_and_checks_arithmetic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saol = root / "saol.jsonl"
            saol_only = root / "saol-only.jsonl"
            ambiguous = root / "ambiguous.jsonl"
            compounds = root / "compounds.jsonl"
            comparison = root / "comparison.json"
            output = root / "unresolved.jsonl"

            saol.write_text(
                json.dumps({"id": "1", "normaliserat_ord": "a"}) + "\n"
                + json.dumps({"id": "2", "normaliserat_ord": "b"}) + "\n"
                + json.dumps({"id": "3", "normaliserat_ord": "c"}) + "\n"
                + json.dumps({"id": "4", "normaliserat_ord": "d"}) + "\n",
                encoding="utf-8",
            )
            saol_only.write_text(
                json.dumps({"record_id": "2", "lemma": "b"}) + "\n"
                + json.dumps({"record_id": "3", "lemma": "c"}) + "\n",
                encoding="utf-8",
            )
            ambiguous.write_text(
                json.dumps({"record_id": "4", "lemma": "d"}) + "\n",
                encoding="utf-8",
            )
            compounds.write_text(
                json.dumps(
                    {
                        "record_id": "3",
                        "head_match_reason": "unique_head_same_upos",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            comparison.write_text(
                json.dumps(
                    {
                        "saol_compared_records": 4,
                        "saol_matched_records": 1,
                    }
                ),
                encoding="utf-8",
            )

            summary = export_unresolved(
                saol,
                saol_only,
                ambiguous,
                compounds,
                comparison,
                output,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(4, summary["total"])
            self.assertEqual(1, summary["direct"])
            self.assertEqual(1, summary["solved_compounds"])
            self.assertEqual(2, summary["records"])
            self.assertEqual(["2", "4"], [row["id"] for row in rows])

    def test_refuses_to_write_when_baseline_count_is_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saol = root / "saol.jsonl"
            saol_only = root / "saol-only.jsonl"
            ambiguous = root / "ambiguous.jsonl"
            compounds = root / "compounds.jsonl"
            comparison = root / "comparison.json"
            output = root / "unresolved.jsonl"

            saol.write_text(json.dumps({"id": "1"}) + "\n", encoding="utf-8")
            saol_only.write_text("", encoding="utf-8")
            ambiguous.write_text("", encoding="utf-8")
            compounds.write_text("", encoding="utf-8")
            comparison.write_text(
                json.dumps(
                    {
                        "saol_compared_records": 1,
                        "saol_matched_records": 0,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Baslinjen stämmer inte"):
                export_unresolved(
                    saol,
                    saol_only,
                    ambiguous,
                    compounds,
                    comparison,
                    output,
                )

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
