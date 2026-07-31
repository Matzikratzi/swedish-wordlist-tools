from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_unresolved import (
    export_unresolved,
    filter_unresolved,
    unresolved_selectors,
)


class ExportUnresolvedTests(unittest.TestCase):
    def test_selects_ambiguous_and_only_unsolved_compounds(self) -> None:
        ambiguous = [{"record_id": "1", "lemma": "ambiguous"}]
        compounds = [
            {
                "record_id": "2",
                "lemma": "olöstord",
                "head_match_reason": "multiple_heads_same_upos",
            },
            {
                "record_id": "3",
                "lemma": "löstord",
                "head_match_reason": "unique_head_same_upos",
            },
        ]

        record_ids, fallback_lemmas = unresolved_selectors(ambiguous, compounds)

        self.assertEqual({"1", "2"}, record_ids)
        self.assertEqual(set(), fallback_lemmas)

    def test_keeps_original_saol_rows_unchanged(self) -> None:
        original = [
            {"id": "1", "normaliserat_ord": "ett", "nested": {"x": 1}},
            {"id": "2", "normaliserat_ord": "två", "nested": {"x": 2}},
        ]

        rows = filter_unresolved(original, {"2"}, set())

        self.assertEqual([original[1]], rows)

    def test_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saol = root / "saol.jsonl"
            ambiguous = root / "ambiguous.jsonl"
            compounds = root / "compounds.jsonl"
            output = root / "unresolved.jsonl"

            saol.write_text(
                json.dumps({"id": "1", "normaliserat_ord": "a"}) + "\n"
                + json.dumps({"id": "2", "normaliserat_ord": "b"}) + "\n"
                + json.dumps({"id": "3", "normaliserat_ord": "c"}) + "\n",
                encoding="utf-8",
            )
            ambiguous.write_text(
                json.dumps({"record_id": "1", "lemma": "a"}) + "\n",
                encoding="utf-8",
            )
            compounds.write_text(
                json.dumps(
                    {
                        "record_id": "2",
                        "lemma": "b",
                        "head_match_reason": "head_not_in_saldo",
                    }
                )
                + json.dumps(
                    {
                        "record_id": "3",
                        "lemma": "c",
                        "head_match_reason": "unique_head_same_upos",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = export_unresolved(saol, ambiguous, compounds, output)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(2, summary["records"])
            self.assertEqual(["1", "2"], [row["id"] for row in rows])


if __name__ == "__main__":
    unittest.main()
