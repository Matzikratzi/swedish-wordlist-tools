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
            ["hög", "högt", "högan"], analyses, {"hög"}
        )

        self.assertEqual(["högan"], only_saol)
        self.assertEqual(["högre", "saldoord", "saldoordet"], only_saldo)
        self.assertEqual(["högre"], [row["form"] for row in candidates])
        self.assertEqual(2, summary["shared_forms"])
        self.assertFalse(summary["affects_game_wordlist"])


if __name__ == "__main__":
    unittest.main()
