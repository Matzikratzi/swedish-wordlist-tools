from __future__ import annotations

import unittest

from swedish_wordlist_tools.audit_saldo_verb_overlap import (
    compare_word_sets,
    normalise_playable_word,
    saldo_forms_for_exact_saol_verbs,
)


class AuditSaldoVerbOverlapTests(unittest.TestCase):
    def test_compares_true_intersection_after_normalisation(self) -> None:
        report = compare_word_sets(
            ["Skriva", "skriver", "skrev", "a", "skriva!"],
            ["skriva", "SKREV", "skrivs", "-"],
            example_limit=10,
        )
        self.assertEqual(3, report["saol_forms"])
        self.assertEqual(3, report["saldo_forms"])
        self.assertEqual(2, report["shared_forms"])
        self.assertEqual(1, report["only_saol_forms"])
        self.assertEqual(1, report["only_saldo_forms"])
        self.assertEqual(["skrev", "skriva"], report["examples"]["shared"])
        self.assertEqual(["skriver"], report["examples"]["only_saol"])
        self.assertEqual(["skrivs"], report["examples"]["only_saldo"])

    def test_reads_raw_saldo_forms_before_fallback_deduplication(self) -> None:
        records = [
            {"upos": "VERB", "normaliserat_ord": "skriva"},
            {"upos": "NOUN", "normaliserat_ord": "akt"},
            {"upos": "VERB", "normaliserat_ord": "saknas"},
        ]
        saldo = {
            "skriva": [
                {
                    "id": "skriva..vb.1",
                    "upos": "VERB",
                    "lemmas": {"skriva"},
                    "forms": {"skriva", "skriver", "skrivs", "skriv-"},
                }
            ]
        }
        forms, verb_records, matched_records = saldo_forms_for_exact_saol_verbs(
            records,
            saldo,
        )
        self.assertEqual(2, verb_records)
        self.assertEqual(1, matched_records)
        self.assertEqual({"skriva", "skriver", "skrivs"}, forms)

    def test_normalises_only_playable_words(self) -> None:
        self.assertEqual("återgå", normalise_playable_word(" ÅTERGÅ "))
        self.assertIsNone(normalise_playable_word("a"))
        self.assertIsNone(normalise_playable_word("gå-ut"))


if __name__ == "__main__":
    unittest.main()
