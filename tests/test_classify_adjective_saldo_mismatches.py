from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_adjective_saldo_mismatches import classify_row


class ClassifyAdjectiveSaldoMismatchesTest(unittest.TestCase):
    def test_explicit_form_is_sent_to_saldo_review(self) -> None:
        row = classify_row({
            "lemma": "bemälde",
            "stycke": "bemälde",
            "missing_forms": [{
                "written_form": "bemälta",
                "slot": "definite_or_plural",
                "provenance": "explicit",
                "source_token": "bemälta",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual("match", form["replay_status"])
        self.assertEqual("needs_saldo_review", form["preliminary_cause"])

    def test_consistent_replace_tail_is_sent_to_source_review(self) -> None:
        row = classify_row({
            "lemma": "allgod",
            "stycke": "all|god",
            "missing_forms": [{
                "written_form": "allgott",
                "slot": "neuter_singular",
                "provenance": "replace_tail",
                "source_token": "-gott",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual("match", form["replay_status"])
        self.assertEqual(
            "generation_consistent_review_saldo_or_saol",
            form["preliminary_cause"],
        )

    def test_consistent_append_is_sent_to_source_review(self) -> None:
        row = classify_row({
            "lemma": "bakåtböjd",
            "stycke": "bakåt|böjd",
            "missing_forms": [{
                "written_form": "bakåtböjda",
                "slot": "definite_or_plural",
                "provenance": "append",
                "source_token": "+a",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual("match", form["replay_status"])
        self.assertEqual(
            "generation_consistent_review_saldo_or_saol",
            form["preliminary_cause"],
        )

    def test_replay_mismatch_points_to_parser_review(self) -> None:
        row = classify_row({
            "lemma": "glad",
            "stycke": "glad",
            "missing_forms": [{
                "written_form": "gladt",
                "slot": "neuter_singular",
                "provenance": "append",
                "source_token": "+t",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual("mismatch", form["replay_status"])
        self.assertEqual("glatt", form["replayed_form"])
        self.assertEqual("needs_parser_review", form["preliminary_cause"])

    def test_missing_lemma_points_to_alignment_review(self) -> None:
        row = classify_row({
            "lemma": "facetterad",
            "stycke": "facetterad",
            "missing_forms": [{
                "written_form": "facetterad",
                "slot": "common_singular",
                "provenance": "lemma",
                "source_token": "",
            }],
        })
        assert row is not None
        form = row["classified_missing_forms"][0]
        self.assertEqual("needs_saldo_alignment_review", form["preliminary_cause"])

    def test_source_correction_is_suspected_saol_error(self) -> None:
        row = classify_row({
            "lemma": "anhörig",
            "stycke": "an|hörig",
            "source_correction_applied": True,
            "missing_forms": [{
                "written_form": "anhöriga",
                "slot": "definite_or_plural",
                "provenance": "append",
                "source_token": "+a",
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
