from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_adjective_saldo_mismatches import classify_row


class ClassifyAdjectiveSaldoMismatchesTest(unittest.TestCase):
    def test_explicit_form_is_saldo_coverage_difference(self) -> None:
        row = classify_row({
            "lemma": "bemälde",
            "effective_notation": "bemälda el. bemälta",
            "missing_forms": [{"written_form": "bemälta", "slot": "definite_or_plural"}],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "explicit")
        self.assertEqual(form["preliminary_cause"], "saldo_coverage_difference")

    def test_replace_tail_requires_parser_or_saldo_review(self) -> None:
        row = classify_row({
            "lemma": "allgod",
            "effective_notation": "-gott +a",
            "missing_forms": [{"written_form": "allgott", "slot": "neuter_singular"}],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "replace_tail")
        self.assertEqual(form["preliminary_cause"], "needs_parser_or_saldo_review")

    def test_second_slot_is_classified_as_append(self) -> None:
        row = classify_row({
            "lemma": "bakåtböjd",
            "effective_notation": "-böjt +a",
            "missing_forms": [{"written_form": "bakåtböjda", "slot": "definite_or_plural"}],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "append")
        self.assertEqual(form["preliminary_cause"], "needs_parser_or_saldo_review")

    def test_lost_prefix_is_flagged_separately(self) -> None:
        row = classify_row({
            "lemma": "förstfödd",
            "effective_notation": "-fött +a",
            "missing_forms": [{"written_form": "fött", "slot": "neuter_singular"}],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "replace_tail")
        self.assertTrue(form["possible_lost_prefix"])
        self.assertEqual(form["preliminary_cause"], "possible_lost_prefix")

    def test_missing_lemma_points_to_alignment(self) -> None:
        row = classify_row({
            "lemma": "facetterad",
            "effective_notation": "fasetterat +e _ facetterat +e",
            "missing_forms": [{"written_form": "facetterad", "slot": "common_singular"}],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "lemma")
        self.assertEqual(form["preliminary_cause"], "saldo_alignment_problem")

    def test_rows_without_missing_forms_are_ignored(self) -> None:
        self.assertIsNone(classify_row({"lemma": "glad", "missing_forms": []}))


if __name__ == "__main__":
    unittest.main()
