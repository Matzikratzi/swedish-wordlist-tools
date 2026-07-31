from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_compound_heads import analyse_row, build_head_index, candidate_dict, recovered_parts
from swedish_wordlist_tools.msd import Msd
from swedish_wordlist_tools.saldo import SaldoAnalysis, SaldoWordForm


def analysis(entry_id: str, upos: str, lemma: str, *forms: str) -> SaldoAnalysis:
    return SaldoAnalysis(
        entry_id=entry_id,
        upos=upos,
        lemmas=frozenset({lemma}),
        word_forms=tuple(SaldoWordForm(form, Msd("")) for form in forms),
    )


class CompoundHeadTests(unittest.TestCase):
    def test_recovers_head_from_truncated_stycke(self) -> None:
        row = {"lemma": "acklimatiseringssvårigheter"}
        split = {"compact_parts": ["acklimatiserings", "svårighete"]}
        self.assertEqual(recovered_parts(row, split), ("acklimatiserings", "svårigheter"))

    def test_unique_same_upos_head(self) -> None:
        saldo = {"avgift": [analysis("avgift..nn.1", "NOUN", "avgift", "avgift", "avgiften", "avgifter")]}
        index = build_head_index(saldo)
        row = {
            "lemma": "abonnemangsavgift",
            "upos": "NOUN",
            "saol_bar_reason": "unique_saol_bar_split",
            "saol_bar_splits": [{"compact_parts": ["abonnemangs", "avgift"]}],
        }
        result = analyse_row(row, index)
        self.assertEqual(result["compound_head"], "avgift")
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["id"], "avgift..nn.1")

    def test_prefers_same_upos(self) -> None:
        saldo = {
            "fri": [
                analysis("fri..av.1", "ADJ", "fri", "fri", "fritt"),
                analysis("fri..ab.1", "ADV", "fri", "fri"),
            ]
        }
        index = build_head_index(saldo)
        row = {
            "lemma": "skattefri",
            "upos": "ADJ",
            "saol_bar_reason": "unique_saol_bar_split",
            "saol_bar_splits": [{"compact_parts": ["skatte", "fri"]}],
        }
        result = analyse_row(row, index)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["upos"], "ADJ")

    def test_matches_exact_inflected_word_form(self) -> None:
        saldo = {"svårighet": [analysis("svårighet..nn.1", "NOUN", "svårighet", "svårighet", "svårigheter")]}
        index = build_head_index(saldo)
        row = {
            "lemma": "acklimatiseringssvårigheter",
            "upos": "NOUN",
            "saol_bar_reason": "unique_saol_bar_split",
            "saol_bar_splits": [{"compact_parts": ["acklimatiserings", "svårigheter"]}],
        }
        result = analyse_row(row, index)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual(result["head_candidates"][0]["id"], "svårighet..nn.1")

    def test_preserves_swedish_diacritics(self) -> None:
        saldo = {
            "not": [analysis("not..nn.1", "NOUN", "not", "not")],
            "nöt": [analysis("nöt..nn.1", "NOUN", "nöt", "nöt", "nötter")],
        }
        index = build_head_index(saldo)
        row = {
            "lemma": "acajounöt",
            "upos": "NOUN",
            "saol_bar_reason": "unique_saol_bar_split",
            "saol_bar_splits": [{"compact_parts": ["acajou", "nöt"]}],
        }
        result = analyse_row(row, index)
        self.assertEqual(result["head_match_reason"], "unique_head_same_upos")
        self.assertEqual([candidate["id"] for candidate in result["head_candidates"]], ["nöt..nn.1"])

    def test_excludes_hyphen_terminated_composition_forms(self) -> None:
        candidate = candidate_dict(
            analysis("grund..nn.1", "NOUN", "grund", "grund", "grund-", "grunden", "grunds", "grunds-")
        )
        self.assertEqual(candidate["forms"], ["grund", "grunden", "grunds"])

    def test_reports_missing_head(self) -> None:
        row = {
            "lemma": "påhittadxyz",
            "upos": "NOUN",
            "saol_bar_reason": "unique_saol_bar_split",
            "saol_bar_splits": [{"compact_parts": ["påhittad", "xyz"]}],
        }
        result = analyse_row(row, {})
        self.assertEqual(result["head_match_reason"], "head_not_in_saldo")

    def test_skips_non_unique_bar_split(self) -> None:
        result = analyse_row({"lemma": "himlabryn", "saol_bar_reason": "saol_bar_does_not_match_lemma"}, {})
        self.assertEqual(result["head_match_reason"], "not_unique_saol_bar_split")


if __name__ == "__main__":
    unittest.main()
