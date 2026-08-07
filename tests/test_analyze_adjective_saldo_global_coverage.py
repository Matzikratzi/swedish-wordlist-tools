from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_saldo_global_coverage import (
    analyze_rows,
    classify_global_presence,
)


class AnalyzeAdjectiveSaldoGlobalCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form_index = {
            "facetterad": [{
                "id": "facetterad..av.1",
                "upos": "ADJ",
                "lemmas": {"facetterad"},
            }],
            "camp": [{
                "id": "camp..nn.1",
                "upos": "NOUN",
                "lemmas": {"camp"},
            }],
        }

    def test_finds_form_in_other_adjective_analysis(self) -> None:
        status, analyses = classify_global_presence("facetterad", self.form_index)
        self.assertEqual("found_in_other_saldo_adjective_analysis", status)
        self.assertEqual("facetterad..av.1", analyses[0]["id"])

    def test_distinguishes_non_adjective_match(self) -> None:
        status, analyses = classify_global_presence("camp", self.form_index)
        self.assertEqual("only_non_adjective_saldo_match", status)
        self.assertEqual("NOUN", analyses[0]["upos"])

    def test_marks_form_absent_from_all_saldo(self) -> None:
        status, analyses = classify_global_presence("campt", self.form_index)
        self.assertEqual("absent_from_all_saldo", status)
        self.assertEqual([], analyses)

    def test_analyze_rows_preserves_existing_classification(self) -> None:
        report, rows = analyze_rows(
            [{
                "lemma": "fasetterad",
                "record_id": "1",
                "classified_missing_forms": [{
                    "written_form": "facetterad",
                    "slot": "common_singular",
                    "provenance": "explicit",
                    "source_token": "facetterat +e",
                    "operation_base": "facetterad",
                }],
            }],
            self.form_index,
        )
        self.assertEqual(1, report["unique_forms"])
        form = rows[0]["classified_missing_forms"][0]
        self.assertEqual("explicit", form["provenance"])
        self.assertEqual(
            "found_in_other_saldo_adjective_analysis",
            form["global_saldo_status"],
        )
        self.assertEqual("saldo_alignment_problem", form["global_review_category"])
        self.assertEqual(1, form["source_occurrence_count"])

    def test_duplicate_forms_across_rows_are_counted_once(self) -> None:
        duplicate = {
            "written_form": "bemälda",
            "slot": "definite_or_plural",
            "provenance": "explicit",
            "source_token": "bemälda",
            "operation_base": "bemälda",
        }
        report, rows = analyze_rows(
            [
                {
                    "lemma": "bemälde",
                    "record_id": "100",
                    "homonym_number": "1",
                    "classified_missing_forms": [duplicate],
                },
                {
                    "lemma": "bemälde",
                    "record_id": "101",
                    "homonym_number": "0",
                    "classified_missing_forms": [dict(duplicate)],
                },
            ],
            self.form_index,
        )
        self.assertEqual(2, report["raw_forms"])
        self.assertEqual(1, report["unique_forms"])
        self.assertEqual(1, report["duplicates_removed"])
        self.assertEqual(1, len(rows))
        form = rows[0]["classified_missing_forms"][0]
        self.assertEqual(2, form["source_occurrence_count"])
        self.assertEqual({"100", "101"}, {
            occurrence["record_id"] for occurrence in form["source_occurrences"]
        })
        self.assertEqual(
            "saldo_coverage_or_saol_review",
            form["global_review_category"],
        )

    def test_different_lemmas_are_not_collapsed(self) -> None:
        form = {
            "written_form": "gemensamma",
            "slot": "definite_or_plural",
            "provenance": "append",
            "source_token": "+a",
        }
        report, _rows = analyze_rows(
            [
                {"lemma": "första", "classified_missing_forms": [form]},
                {"lemma": "andra", "classified_missing_forms": [dict(form)]},
            ],
            self.form_index,
        )
        self.assertEqual(2, report["unique_forms"])


if __name__ == "__main__":
    unittest.main()
