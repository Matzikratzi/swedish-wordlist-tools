from __future__ import annotations

import unittest

from swedish_wordlist_tools.audit_final_wordlist_saldo import audit
from swedish_wordlist_tools.msd import parse_msd
from swedish_wordlist_tools.saldo import SaldoAnalysis, SaldoWordForm


class AuditFinalWordlistSaldoTests(unittest.TestCase):
    def test_reports_global_sets_and_same_lemma_candidates_without_filtering(self) -> None:
        analyses = [
            SaldoAnalysis(
                entry_id="hög..av.1",
                upos="ADJ",
                lemmas=frozenset({"hög"}),
                word_forms=(
                    SaldoWordForm("högt", parse_msd("pos indef sg n")),
                    SaldoWordForm("högre", parse_msd("komp")),
                    SaldoWordForm("hög-", parse_msd("sms")),
                ),
            ),
            SaldoAnalysis(
                entry_id="saldoord..nn.1",
                upos="NOUN",
                lemmas=frozenset({"saldoord"}),
                word_forms=(SaldoWordForm("saldoordet", parse_msd("sg def nom")),),
            ),
        ]
        summary, only_saol, only_saldo, candidates = audit(
            ["hög", "högt", "högan"], analyses, {"hög": {"ADJ"}}, {
                "hög": [{"record_id": "1", "upos": ["ADJ"], "ordkl": "adj.", "notation": "+t +a"}],
            }
        )

        self.assertEqual(["högan"], only_saol)
        self.assertEqual(["högre", "saldoord", "saldoordet"], only_saldo)
        self.assertEqual(["högre"], [row["form"] for row in candidates])
        self.assertEqual("COMPARISON", candidates[0]["primary_category"])
        self.assertEqual("+t +a", candidates[0]["matching_saol_articles"][0]["notation"])
        self.assertEqual(2, summary["shared_forms"])
        self.assertFalse(summary["affects_game_wordlist"])

    def test_requires_same_word_class_for_review_candidate(self) -> None:
        analyses = [SaldoAnalysis(
            entry_id="fil..vb.1",
            upos="VERB",
            lemmas=frozenset({"fil"}),
            word_forms=(SaldoWordForm("filade", parse_msd("pret ind aktiv")),),
        )]
        summary, _only_saol, _only_saldo, candidates = audit(
            ["fil"], analyses, {"fil": {"NOUN"}},
        )
        self.assertEqual([], candidates)
        self.assertEqual(0, summary["saldo_only_with_exact_saol_lemma_and_upos_candidates"])


if __name__ == "__main__":
    unittest.main()
