from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_unresolved import collect_unresolved, export_unresolved


class CollectUnresolvedTests(unittest.TestCase):
    def test_combines_ambiguous_and_only_unsolved_compounds(self) -> None:
        ambiguous = [
            {
                "lemma": "ambiguous",
                "upos": "NOUN",
                "reason": "lemma_match_but_word_class_not_resolved",
                "saldo_analyses": [
                    {"id": "a..nn.1", "upos": "NOUN", "lemmas": ["a"]},
                    {"id": "a..vb.1", "upos": "VERB", "lemmas": ["a"]},
                ],
            }
        ]
        compounds = [
            {
                "lemma": "olöstord",
                "upos": "NOUN",
                "head_match_reason": "multiple_heads_same_upos",
                "compound_left": "olöst",
                "compound_head": "ord",
                "head_candidates": [
                    {"id": "ord..nn.1", "upos": "NOUN", "lemmas": ["ord"]},
                    {"id": "ord..nn.2", "upos": "NOUN", "lemmas": ["ord"]},
                ],
            },
            {
                "lemma": "löstord",
                "head_match_reason": "unique_head_same_upos",
            },
        ]

        rows = collect_unresolved(ambiguous, compounds)

        self.assertEqual(2, len(rows))
        by_lemma = {row["lemma"]: row for row in rows}
        self.assertEqual("saldo_ambiguous", by_lemma["ambiguous"]["source_group"])
        self.assertEqual(2, by_lemma["ambiguous"]["candidate_count"])
        self.assertEqual("compound", by_lemma["olöstord"]["source_group"])
        self.assertEqual(3, by_lemma["olöstord"]["compound_head_length"])
        self.assertNotIn("löstord", by_lemma)

    def test_writes_json_csv_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ambiguous = root / "ambiguous.jsonl"
            compounds = root / "compounds.jsonl"
            output_json = root / "unresolved.json"
            output_csv = root / "unresolved.csv"
            summary_path = root / "summary.json"

            ambiguous.write_text(
                json.dumps({"lemma": "a", "reason": "ambiguous"}) + "\n",
                encoding="utf-8",
            )
            compounds.write_text(
                json.dumps(
                    {
                        "lemma": "b",
                        "head_match_reason": "head_not_in_saldo",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = export_unresolved(
                ambiguous,
                compounds,
                output_json,
                output_csv,
                summary_path,
            )

            self.assertEqual(2, summary["records"])
            self.assertEqual(2, len(json.loads(output_json.read_text(encoding="utf-8"))))
            self.assertTrue(output_csv.read_text(encoding="utf-8").startswith("source_group,"))
            self.assertEqual(2, json.loads(summary_path.read_text(encoding="utf-8"))["records"])


if __name__ == "__main__":
    unittest.main()
