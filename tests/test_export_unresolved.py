from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_unresolved import (
    export_unresolved,
    filter_by_counts,
    selector_counts,
    solved_compound_counts,
    subtract_counts,
)


class ExportUnresolvedTests(unittest.TestCase):
    def test_subtracts_only_solved_compounds(self) -> None:
        baseline = selector_counts(
            [
                {"record_id": "1", "lemma": "ambiguous"},
                {"record_id": "2", "lemma": "olöstord"},
                {"record_id": "3", "lemma": "löstord"},
            ]
        )
        solved = solved_compound_counts(
            [
                {"record_id": "2", "lemma": "olöstord", "head_match_reason": "multiple_heads_same_upos"},
                {"record_id": "3", "lemma": "löstord", "head_match_reason": "unique_head_same_upos"},
            ]
        )
        remaining, removed = subtract_counts(baseline, solved)
        original = [
            {"id": "1", "normaliserat_ord": "ambiguous"},
            {"id": "2", "normaliserat_ord": "olöstord"},
            {"id": "3", "normaliserat_ord": "löstord"},
            {"id": "4", "normaliserat_ord": "direktlöst"},
        ]

        rows = filter_by_counts(original, remaining)

        self.assertEqual(1, removed)
        self.assertEqual(["1", "2"], [row["id"] for row in rows])

    def test_preserves_duplicate_records(self) -> None:
        report_rows = [
            {"record_id": "7", "lemma": "dublett"},
            {"record_id": "7", "lemma": "dublett"},
        ]
        original = [
            {"id": "7", "normaliserat_ord": "dublett", "value": 1},
            {"id": "7", "normaliserat_ord": "dublett", "value": 2},
        ]

        rows = filter_by_counts(original, selector_counts(report_rows))

        self.assertEqual(original, rows)
        self.assertEqual(2, sum(selector_counts(report_rows).values()))

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
                "".join(
                    json.dumps({"id": str(i), "normaliserat_ord": letter}) + "\n"
                    for i, letter in enumerate("abcd", start=1)
                ),
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
                json.dumps({"record_id": "3", "lemma": "c", "head_match_reason": "unique_head_same_upos"}) + "\n",
                encoding="utf-8",
            )
            comparison.write_text(
                json.dumps({"saol_compared_records": 4, "saol_matched_records": 1}),
                encoding="utf-8",
            )

            summary = export_unresolved(saol, saol_only, ambiguous, compounds, comparison, output)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(1, summary["solved_compounds"])
            self.assertEqual(2, summary["records"])
            self.assertEqual(["2", "4"], [row["id"] for row in rows])

    def test_refuses_wrong_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / name for name in ("saol", "only", "ambiguous", "compounds", "comparison", "output")}
            paths["saol"].write_text(json.dumps({"id": "1"}) + "\n", encoding="utf-8")
            for name in ("only", "ambiguous", "compounds"):
                paths[name].write_text("", encoding="utf-8")
            paths["comparison"].write_text(
                json.dumps({"saol_compared_records": 1, "saol_matched_records": 0}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Baslinjen stämmer inte"):
                export_unresolved(
                    paths["saol"], paths["only"], paths["ambiguous"],
                    paths["compounds"], paths["comparison"], paths["output"]
                )
            self.assertFalse(paths["output"].exists())


if __name__ == "__main__":
    unittest.main()
