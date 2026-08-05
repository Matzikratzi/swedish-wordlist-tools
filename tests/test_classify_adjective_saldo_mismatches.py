from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_adjective_saldo_mismatches import classify_row


class ClassifyAdjectiveSaldoMismatchesTest(unittest.TestCase):
    def test_explicit_form_is_sent_to_saldo_review(self) -> None:
        row = classify_row({
            "lemma": "bemälde",
            "missing_forms": [{
                "written_form": "bemälta",
                "slot": "definite_or_plural",
                "provenance": "explicit",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "explicit")
        self.assertEqual(form["preliminary_cause"], "needs_saldo_review")

    def test_replace_tail_requires_manual_review(self) -> None:
        row = classify_row({
            "lemma": "allgod",
            "missing_forms": [{
                "written_form": "allgott",
                "slot": "neuter_singular",
                "provenance": "replace_tail",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "replace_tail")
        self.assertEqual(form["preliminary_cause"], "needs_manual_review")

    def test_append_provenance_requires_manual_review(self) -> None:
        row = classify_row({
            "lemma": "bakåtböjd",
            "effective_notation": "deliberately ignored",
            "missing_forms": [{
                "written_form": "bakåtböjda",
                "slot": "definite_or_plural",
                "provenance": "append",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "append")
        self.assertEqual(form["preliminary_cause"], "needs_manual_review")

    def test_missing_lemma_points_to_alignment_review(self) -> None:
        row = classify_row({
            "lemma": "facetterad",
            "missing_forms": [{
                "written_form": "facetterad",
                "slot": "common_singular",
                "provenance": "lemma",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual(form["derivation"], "lemma")
        self.assertEqual(form["preliminary_cause"], "needs_saldo_alignment_review")

    def test_source_correction_is_suspected_saol_error(self) -> None:
        row = classify_row({
            "lemma": "anhörig",
            "source_correction_applied": True,
            "missing_forms": [{
                "written_form": "anhöriga",
                "slot": "definite_or_plural",
                "provenance": "append",
            }],
        })
        assert row is not None
        self.assertEqual(
            "suspected_saol_error",
            row["classified_missing_forms"][0]["preliminary_cause"],
        )

    def test_rows_without_missing_forms_are_ignored(self) -> None:
        self.assertIsNone(classify_row({"lemma": "glad", "missing_forms": []}))


if __name__ == "__main__":
    unittest.main()
