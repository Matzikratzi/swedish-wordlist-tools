from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_slots import interpret_simple_adjective_slots


class AdjectiveSlotsTests(unittest.TestCase):
    def parse(self, lemma: str, text: str):
        slots = interpret_simple_adjective_slots({"normaliserat_ord": lemma, "text": text, "upos": "ADJ"})
        self.assertIsNotNone(slots)
        return slots

    def test_regular_t_a_applies_neuter_spelling(self) -> None:
        slots = self.parse("glad", "+t +a")
        self.assertEqual(("glad", "glatt", "glada"), slots.written_forms())
        self.assertEqual("regular_t_a", slots.rule)

    def test_final_rd_and_ld_drop_d_before_t(self) -> None:
        self.assertEqual(("hård", "hårt", "hårda"), self.parse("hård", "+t +a").written_forms())
        self.assertEqual(("vild", "vilt", "vilda"), self.parse("vild", "+t +a").written_forms())

    def test_other_final_d_becomes_tt(self) -> None:
        self.assertEqual(("röd", "rött", "röda"), self.parse("röd", "+t +a").written_forms())

    def test_unchanged_neuter(self) -> None:
        self.assertEqual(("kortväxt", "kortväxt", "kortväxta"), self.parse("kortväxt", "n. +, +a").written_forms())

    def test_regular_tt_a(self) -> None:
        self.assertEqual(("blå", "blått", "blåa"), self.parse("blå", "+tt +a").written_forms())

    def test_regular_t_ma(self) -> None:
        self.assertEqual(("öm", "ömt", "ömma"), self.parse("öm", "+t +ma").written_forms())

    def test_explicit_pairs(self) -> None:
        self.assertEqual(("mångfärgad", "mångfärgat", "mångfärgade"), self.parse("mångfärgad", "-färgat +e").written_forms())
        self.assertEqual(("obunden", "obundet", "obundna"), self.parse("obunden", "-bundet -bundna").written_forms())
        self.assertEqual(("osäker", "osäkert", "osäkra"), self.parse("osäker", "+t -säkra").written_forms())
        self.assertEqual(("bebodd", "bebott", "bebodda"), self.parse("bebodd", "bebott bebodda").written_forms())

    def test_labelled_plural_alternatives(self) -> None:
        slots = self.parse("akvamarinblå", "-blått, best. och: pl. + el. +a")
        self.assertEqual(("akvamarinblå", "akvamarinblått", "akvamarinblå", "akvamarinblåa"), slots.written_forms())

    def test_labelled_limited_plural_suffix(self) -> None:
        slots = self.parse("fullmäktig", "pl. +e")
        self.assertEqual(("fullmäktig", "fullmäktige"), slots.written_forms())
        self.assertEqual("labelled_limited_paradigm", slots.rule)

    def test_labelled_limited_explicit_plural(self) -> None:
        self.assertEqual(("bitteliten", "bittesmå"), self.parse("bitteliten", "pl. bittesmå").written_forms())

    def test_labelled_masculine_and_bare_definite(self) -> None:
        self.assertEqual(("främsta", "främste"), self.parse("främsta", "mask. främste").written_forms())
        self.assertEqual(("flesta",), self.parse("flesta", "best.").written_forms())

    def test_comparison_only_suffixes(self) -> None:
        self.assertEqual(("ringa", "ringare", "ringast"), self.parse("ringa", "komp. +re, superl. +st").written_forms())

    def test_comparison_only_explicit_forms(self) -> None:
        self.assertEqual(("få", "färre", "färst"), self.parse("få", "komp. färre, superl. färst").written_forms())

    def test_positive_with_labelled_comparison(self) -> None:
        self.assertEqual(("förnäm", "förnämt", "förnäma", "förnämare", "förnämst", "förnämast"), self.parse("förnäm", "+t +a, komp. +are, superl. +st H +ast").written_forms())

    def test_explicit_positive_and_comparison(self) -> None:
        self.assertEqual(("god", "gott", "goda", "bättre", "bäst"), self.parse("god", "gott goda, bättre bäst").written_forms())

    def test_rejects_truncated_comparison(self) -> None:
        self.assertIsNone(interpret_simple_adjective_slots({"normaliserat_ord": "nära", "text": "komp. närmare el. närmre, superl. närmast el. närm"}))


if __name__ == "__main__":
    unittest.main()
