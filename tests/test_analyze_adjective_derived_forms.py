from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_adjective_derived_forms import build_rows, build_summary


class AnalyzeAdjectiveDerivedFormsTests(unittest.TestCase):
    def test_classifies_derived_forms_against_same_lemma_adjective_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adjectives = root / "adjectives.jsonl"
            saldo = root / "saldo.jsonl"
            adjective_row = {
                "lemma": "liten",
                "homonym_number": "1",
                "source_notation": "litet; mindre minst",
                "forms": [
                    {"written_form": "minst", "slot": "superlative", "provenance": "explicit"},
                    {"written_form": "minsta", "slot": "superlative_definite_or_plural", "provenance": "derived_inflection"},
                    {"written_form": "minste", "slot": "superlative_masculine_definite", "provenance": "derived_inflection"},
                ],
            }
            adjectives.write_text(json.dumps(adjective_row, ensure_ascii=False) + "\n", encoding="utf-8")
            saldo.write_text(
                json.dumps(
                    {
                        "id": "liten..av.1",
                        "upos": "ADJ",
                        "lemmas": ["liten"],
                        "forms": ["liten", "minst", "minsta"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            rows = build_rows(adjectives, saldo)
            summary = build_summary(rows)

        by_form = {row["derived_form"]: row for row in rows}
        self.assertEqual("confirmed_by_saldo", by_form["minsta"]["status"])
        self.assertEqual("missing_from_saldo", by_form["minste"]["status"])
        self.assertEqual(
            {"confirmed_by_saldo": 1, "missing_from_saldo": 1},
            summary["status_counts"],
        )

    def test_reports_missing_saldo_lemma_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adjectives = root / "adjectives.jsonl"
            saldo = root / "saldo.jsonl"
            adjectives.write_text(
                json.dumps(
                    {
                        "lemma": "okänd",
                        "forms": [
                            {"written_form": "okändast", "slot": "superlative", "provenance": "explicit"},
                            {"written_form": "okändaste", "slot": "superlative_definite_or_plural", "provenance": "derived_inflection"},
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            saldo.write_text("", encoding="utf-8")
            rows = build_rows(adjectives, saldo)
        self.assertEqual("lemma_missing_in_saldo", rows[0]["status"])


if __name__ == "__main__":
    unittest.main()
