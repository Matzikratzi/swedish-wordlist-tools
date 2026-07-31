from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_compound_heads import (
    analyse_row,
    build_head_indexes,
    candidate_dict,
    recovered_parts,
)
from swedish_wordlist_tools.msd import Msd
from swedish_wordlist_tools.saldo import SaldoAnalysis, SaldoWordForm


def analysis(entry_id: str, upos: str, lemma: str, *forms: str) -> SaldoAnalysis:
    return SaldoAnalysis(
        entry_id=entry_id,
        upos=upos,
        lemmas=frozenset({lemma}),
        word_forms=tuple(SaldoWordForm(form, Msd("")) for form in forms),
    )


def analysis_with_msd(entry_id: str, upos: str, lemma: str, *forms: tuple[str, str]) -> SaldoAnalysis:
    return SaldoAnalysis(
        entry_id=entry_id,
        upos=upos,
        lemmas=frozenset({lemma}),
        word_forms=tuple(SaldoWordForm(written_form, Msd(msd)) for written_form, msd in forms),
    )


class CompoundHeadTests(unittest.TestCase):
    def test_recovers_head_from_truncated_stycke(self) -> None:
        row = {"lemma": "acklimatiseringssvårigheter"}
        split = {"compact_parts": ["acklimatiserings", "svårighete"]}
        self.assertEqual(recovered_parts(row, split), ("acklimatiserings", "svårigheter"))

    def analyse(self, row: dict[str, object], saldo: dict[str, list[SaldoAnalysis]]):
        lemma_index, form_index = build_head_indexes(saldo)
        return analyse_row(row, lemma_index, form_index)

    def test_unique_same_upos_head(self) -> None:
        saldo = {"avgift": [analysis("avgift..nn.1", "NOUN", "avgift", "avgift", "avgiften", "avgifter")]}
        row = {"lemma": "abonnemangsavgift", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["abonnemangs", "avgift"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["compound_head"], "avgift")
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["id"], "avgift..nn.1")

    def test_prefers_same_upos(self) -> None:
        saldo = {"fri": [analysis("fri..av.1", "ADJ", "fri", "fri", "fritt"), analysis("fri..ab.1", "ADV", "fri", "fri")]}
        row = {"lemma": "skattefri", "upos": "ADJ", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["skatte", "fri"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["upos"], "ADJ")

    def test_uses_only_compatible_exact_lemma_candidates_when_available(self) -> None:
        saldo = {"val": [analysis("val..nn.1", "NOUN", "val", "val", "valet")],
                 "vala": [analysis("vala..vb.1", "VERB", "vala", "val", "valar")]}
        row = {"lemma": "språkval", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["språk", "val"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual([candidate["id"] for candidate in result["head_candidates"]], ["val..nn.1"])

    def test_falls_back_to_exact_inflected_word_form(self) -> None:
        saldo = {"svårighet": [analysis("svårighet..nn.1", "NOUN", "svårighet", "svårighet", "svårigheter")]}
        row = {"lemma": "acklimatiseringssvårigheter", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["acklimatiserings", "svårigheter"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["id"], "svårighet..nn.1")

    def test_matches_adjective_to_present_participle_word_form(self) -> None:
        saldo = {"framkalla": [analysis_with_msd(
            "framkalla..vb.1", "VERB", "framkalla",
            ("framkalla", "inf aktiv"), ("framkallande", "pres_part nom"),
        )]}
        row = {"lemma": "abortframkallande", "upos": "ADJ", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["abort", "framkallande"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["id"], "framkalla..vb.1")
        self.assertEqual(result["head_candidates"][0]["matched_word_forms"], [
            {"written_form": "framkallande", "msd": "pres_part nom"}
        ])

    def test_participle_fallback_bypasses_incompatible_exact_noun_lemma(self) -> None:
        saldo = {
            "framkallande": [analysis("framkallande..nn.1", "NOUN", "framkallande", "framkallandet")],
            "framkalla": [analysis_with_msd(
                "framkalla..vb.1", "VERB", "framkalla",
                ("framkallande", "pres_part nom"),
            )],
        }
        row = {"lemma": "abortframkallande", "upos": "ADJ", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["abort", "framkallande"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual([candidate["id"] for candidate in result["head_candidates"]], ["framkalla..vb.1"])
        self.assertEqual(result["head_candidates"][0]["matched_word_forms"], [
            {"written_form": "framkallande", "msd": "pres_part nom"}
        ])

    def test_does_not_treat_non_participle_verb_form_as_adjective(self) -> None:
        saldo = {"kalla": [analysis_with_msd("kalla..vb.1", "VERB", "kalla", ("kallar", "pres ind aktiv"))]}
        row = {"lemma": "specialkallar", "upos": "ADJ", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["special", "kallar"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_upos_mismatch")

    def test_non_adjective_does_not_bypass_incompatible_exact_lemma(self) -> None:
        saldo = {
            "saker": [analysis("saker..av.1", "ADJ", "saker", "saker")],
            "sak": [analysis_with_msd("sak..nn.1", "NOUN", "sak", ("saker", "pl indef nom"))],
        }
        row = {"lemma": "julsaker", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["jul", "saker"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_upos_mismatch")
        self.assertEqual([candidate["id"] for candidate in result["head_candidates"]], ["saker..av.1"])

    def test_accepts_candidate_when_same_form_has_supine_and_participle_msds(self) -> None:
        saldo = {
            "belysa": [analysis_with_msd(
                "belysa..vb.1", "VERB", "belysa",
                ("belyst", "sup aktiv"),
                ("belyst", "pret_part indef sg u nom"),
            )],
        }
        row = {"lemma": "fasadbelyst", "upos": "ADJ", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["fasad", "belyst"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(
            result["head_candidates"][0]["matched_word_forms"],
            [
                {"written_form": "belyst", "msd": "sup aktiv"},
                {"written_form": "belyst", "msd": "pret_part indef sg u nom"},
            ],
        )

    def test_preserves_swedish_diacritics(self) -> None:
        saldo = {"not": [analysis("not..nn.1", "NOUN", "not", "not")], "nöt": [analysis("nöt..nn.1", "NOUN", "nöt", "nöt", "nötter")]}
        row = {"lemma": "acajounöt", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["acajou", "nöt"]}]}
        result = self.analyse(row, saldo)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual([candidate["id"] for candidate in result["head_candidates"]], ["nöt..nn.1"])

    def test_excludes_hyphen_terminated_composition_forms(self) -> None:
        saldo = {"grund": [analysis("grund..nn.1", "NOUN", "grund", "grund", "grund-", "grunden", "grunds", "grunds-")]}
        lemma_index, form_index = build_head_indexes(saldo)
        self.assertNotIn("grunds", lemma_index)
        self.assertIn("grunds", form_index)
        self.assertNotIn("grund-", form_index)
        candidate = candidate_dict(saldo["grund"][0])
        self.assertEqual(candidate["forms"], ["grund", "grunden", "grunds"])

    def test_reports_missing_head(self) -> None:
        row = {"lemma": "påhittadxyz", "upos": "NOUN", "saol_bar_reason": "unique_saol_bar_split",
               "saol_bar_splits": [{"compact_parts": ["påhittad", "xyz"]}]}
        result = analyse_row(row, {}, {})
        self.assertEqual(result["head_match_reason"], "head_not_in_saldo")

    def test_skips_non_unique_bar_split(self) -> None:
        result = analyse_row({"lemma": "himlabryn", "saol_bar_reason": "saol_bar_does_not_match_lemma"}, {}, {})
        self.assertEqual(result["head_match_reason"], "not_unique_saol_bar_split")


if __name__ == "__main__":
    unittest.main()
