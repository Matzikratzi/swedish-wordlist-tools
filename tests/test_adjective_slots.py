from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_slots import interpret_simple_adjective_slots


class AdjectiveSlotsTests(unittest.TestCase):
    def parse(self, lemma: str, text: str):
        slots = interpret_simple_adjective_slots({"normaliserat_ord": lemma, "text": text, "upos": "ADJ"})
        self.assertIsNotNone(slots)
        return slots

    def test_regular_t_a_applies_neuter_spelling(self) -> None:
        self.assertEqual(("glad", "glatt", "glada"), self.parse("glad", "+t +a").written_forms())
        self.assertEqual(("hård", "hårt", "hårda"), self.parse("hård", "+t +a").written_forms())
        self.assertEqual(("vild", "vilt", "vilda"), self.parse("vild", "+t +a").written_forms())
        self.assertEqual(("röd", "rött", "röda"), self.parse("röd", "+t +a").written_forms())

    def test_basic_patterns(self) -> None:
        self.assertEqual(("kortväxt", "kortväxta"), self.parse("kortväxt", "n. +, +a").written_forms())
        self.assertEqual(("blå", "blått", "blåa"), self.parse("blå", "+tt +a").written_forms())
        self.assertEqual(("öm", "ömt", "ömma"), self.parse("öm", "+t +ma").written_forms())

    def test_explicit_pairs(self) -> None:
        self.assertEqual(("mångfärgad", "mångfärgat", "mångfärgade"), self.parse("mångfärgad", "-färgat +e").written_forms())
        self.assertEqual(("obunden", "obundet", "obundna"), self.parse("obunden", "-bundet -bundna").written_forms())
        self.assertEqual(("osäker", "osäkert", "osäkra"), self.parse("osäker", "+t -säkra").written_forms())
        self.assertEqual(("bebodd", "bebott", "bebodda"), self.parse("bebodd", "bebott bebodda").written_forms())

    def test_labels_and_limited_slots(self) -> None:
        self.assertEqual(("akvamarinblå", "akvamarinblått", "akvamarinblåa"), self.parse("akvamarinblå", "-blått, best. och: pl. + el. +a").written_forms())
        self.assertEqual(("blå", "blått", "blåa"), self.parse("blå", "blått, best. och: pl. blå el. blåa").written_forms())
        self.assertEqual(("fullmäktig", "fullmäktige"), self.parse("fullmäktig", "pl. +e").written_forms())
        self.assertEqual(("bitteliten", "bittesmå"), self.parse("bitteliten", "pl. bittesmå").written_forms())
        self.assertEqual(("främsta", "främste"), self.parse("främsta", "mask. främste").written_forms())
        self.assertEqual(("flesta",), self.parse("flesta", "best.").written_forms())

    def test_single_slot_patterns(self) -> None:
        self.assertEqual(("dan", "dant"), self.parse("dan", "+t").written_forms())
        slots = self.parse("genomsvett", "n. +")
        self.assertEqual(("genomsvett",), slots.written_forms())
        self.assertEqual(2, len(slots.forms))
        self.assertEqual(("hot", "hotta"), self.parse("hot", "neutr. +; pl. hotta").written_forms())
        self.assertEqual(("förstnämnde", "förstnämnda"), self.parse("förstnämnde", "förstnämnda").written_forms())

    def test_parallel_alternatives(self) -> None:
        self.assertEqual(("fasetterad", "fasetterat", "fasetterade", "facetterad", "facetterat", "facetterade"), self.parse("fasetterad", "fasetterat +e _ facetterat +e").written_forms())
        self.assertEqual(("hårdflörtad", "hårdflörtat", "hårdflörtade", "hårdflirtad", "hårdflirtat", "hårdflirtade"), self.parse("hårdflörtad", "-flörtat +e _ -flirtat +e").written_forms())
        self.assertEqual(("ledsen", "ledset", "ledsna", "lesset", "lessna"), self.parse("ledsen", "ledset ledsna _ lesset lessna").written_forms())

    def test_generic_comment_and_replacement_notation(self) -> None:
        self.assertEqual(("perenn", "perent", "perenna"), self.parse("perenn", "perent [-en>t] +a").written_forms())
        self.assertEqual(("hög", "högt", "höga", "högre", "högst"), self.parse("hög", "högt [hök>t] höga, högre högst [hök>st]").written_forms())
        self.assertEqual(("reliabel", "reliabelt", "reliabla"), self.parse("reliabel", "+-t reliabla").written_forms())

    def test_generic_explicit_and_alternative_slots(self) -> None:
        self.assertEqual(("juste", "justa"), self.parse("juste", "n. +, justa").written_forms())
        self.assertEqual(("bemälde", "bemälda", "bemälta"), self.parse("bemälde", "bemälda el. bemälta").written_forms())
        self.assertEqual(("trång", "trångt", "trängre", "trångare", "trängst", "trångast"), self.parse("trång", "+t, trängre H +are, trängst H +ast").written_forms())

    def test_parallel_variant_with_shared_suffix_notation(self) -> None:
        self.assertEqual(
            ("sjangdobel", "sjangdobelt", "sjangdobla", "schangdobel", "schangdobelt", "schangdobla"),
            self.parse("sjangdobel", "+t sjangdobla _ +t schangdobla").written_forms(),
        )

    def test_comparison(self) -> None:
        self.assertEqual(("ringa", "ringare", "ringast"), self.parse("ringa", "komp. +re, superl. +st").written_forms())
        self.assertEqual(("få", "färre", "färst"), self.parse("få", "komp. färre, superl. färst").written_forms())
        self.assertEqual(("förnäm", "förnämt", "förnäma", "förnämare", "förnämst", "förnämast"), self.parse("förnäm", "+t +a, komp. +are, superl. +st H +ast").written_forms())
        self.assertEqual(("god", "gott", "goda", "bättre", "bäst"), self.parse("god", "gott goda, bättre bäst").written_forms())

    def test_rejects_truncated_comparison(self) -> None:
        self.assertIsNone(interpret_simple_adjective_slots({"normaliserat_ord": "nära", "text": "komp. närmare el. närmre, superl. närmast el. närm"}))


if __name__ == "__main__":
    unittest.main()
