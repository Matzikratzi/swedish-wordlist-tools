from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry, normalise_pattern
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounParadigmTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_completes_n_er_noun(self) -> None:
        entry = self.complete("idé", "+n +er")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"idé", "idés", "idén", "idéns", "idéer", "idéers", "idéerna", "idéernas"},
            set(entry.forms if entry else ()),
        )

    def test_normalises_stress_marked_n_er_noun(self) -> None:
        self.assertEqual("+n +er", normalise_pattern("+n +er [-o>r-]"))
        entry = self.complete("reaktor", "+n +er [-o>r-]")
        self.assertIsNotNone(entry)
        self.assertEqual("+n +er", entry.pattern if entry else None)
        self.assertEqual(
            {
                "reaktor", "reaktors", "reaktorn", "reaktorns",
                "reaktorer", "reaktorers", "reaktorerna", "reaktorernas",
            },
            set(entry.forms if entry else ()),
        )
        self.assertNotIn("reakto", set(entry.forms if entry else ()))
        self.assertNotIn("r", set(entry.forms if entry else ()))

    def test_completes_pronunciation_marked_n_r_noun(self) -> None:
        entry = self.complete("baguette", "+n [-en]; pl. +r [-er]")
        self.assertIsNotNone(entry)
        self.assertEqual("+n +r", entry.pattern if entry else None)
        self.assertEqual(
            {
                "baguette", "baguettes", "baguetten", "baguettens",
                "baguetter", "baguetters", "baguetterna", "baguetternas",
            },
            set(entry.forms if entry else ()),
        )

    def test_completes_pronunciation_marked_t_noun(self) -> None:
        entry = self.complete("arbitrage", "+t [-et]")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"arbitrage", "arbitrages", "arbitraget", "arbitragets"},
            set(entry.forms if entry else ()),
        )

    def test_completes_en_ar_noun(self) -> None:
        entry = self.complete("hund", "+en +ar")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"hund", "hunds", "hunden", "hundens", "hundar", "hundars", "hundarna", "hundarnas"},
            set(entry.forms if entry else ()),
        )

    def test_completes_et_er_neuter(self) -> None:
        entry = self.complete("parti", "+et +er")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"parti", "partis", "partiet", "partiets", "partier", "partiers", "partierna", "partiernas"},
            set(entry.forms if entry else ()),
        )

    def test_completes_zero_plural_neuter(self) -> None:
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"hus", "huset", "husets", "husen", "husens"},
            set(entry.forms if entry else ()),
        )

    def test_completes_zero_plural_neuter_after_final_e(self) -> None:
        entry = self.complete("apanage", "+t [-et]; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"apanage", "apanages", "apanaget", "apanagets", "apanagen", "apanagens"},
            set(entry.forms if entry else ()),
        )
        self.assertNotIn("apanageen", set(entry.forms if entry else ()))

    def test_zero_plural_neuter_without_final_e_still_takes_en(self) -> None:
        entry = self.complete("ansvar", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertIn("ansvaren", set(entry.forms if entry else ()))
        self.assertIn("ansvarens", set(entry.forms if entry else ()))

    def test_completes_n_zero_plural_noun(self) -> None:
        entry = self.complete("demo", "+n; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"demo", "demos", "demon", "demons", "demona", "demonas"},
            set(entry.forms if entry else ()),
        )

    def test_completes_t_n_neuter(self) -> None:
        entry = self.complete("alibi", "+t +n")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"alibi", "alibis", "alibit", "alibits", "alibin", "alibins", "alibina", "alibinas"},
            set(entry.forms if entry else ()),
        )

    def test_completes_en_singular_only_noun(self) -> None:
        entry = self.complete("mjölk", "+en")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"mjölk", "mjölks", "mjölken", "mjölkens"},
            set(entry.forms if entry else ()),
        )

    def test_completes_n_singular_only_noun(self) -> None:
        entry = self.complete("afasi", "+n")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"afasi", "afasis", "afasin", "afasins"},
            set(entry.forms if entry else ()),
        )

    def test_completes_et_singular_only_noun(self) -> None:
        entry = self.complete("ansvar", "+et")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"ansvar", "ansvars", "ansvaret", "ansvarets"},
            set(entry.forms if entry else ()),
        )

    def test_completes_t_singular_only_noun(self) -> None:
        entry = self.complete("foto", "+t")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"foto", "fotos", "fotot", "fotots"},
            set(entry.forms if entry else ()),
        )

    def test_completes_explicit_used_plural_in_anden(self) -> None:
        for lemma, plural in (
            ("anmodan", "anmodanden"),
            ("strävan", "strävanden"),
            ("yrkan", "yrkanden"),
            ("vädjan", "vädjanden"),
        ):
            with self.subTest(lemma=lemma):
                entry = self.complete(
                    lemma,
                    f"best. +; i: pl. används: {plural}",
                )
                self.assertIsNotNone(entry)
                self.assertEqual(
                    {
                        lemma, lemma + "s", plural, plural + "s",
                        plural + "a", plural + "as",
                    },
                    set(entry.forms if entry else ()),
                )

    def test_completes_explicit_used_plural_in_ar(self) -> None:
        entry = self.complete(
            "ansökan",
            "best. +; i: pl. används: ansökningar",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "ansökan", "ansökans", "ansökningar", "ansökningars",
                "ansökningarna", "ansökningarnas",
            },
            set(entry.forms if entry else ()),
        )
        self.assertNotIn("ansökningara", set(entry.forms if entry else ()))

    def test_completes_compound_explicit_used_plural(self) -> None:
        entry = self.complete(
            "fredssträvan",
            "best. +; i: pl. används: -strävanden",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "fredssträvan", "fredssträvans", "fredssträvanden",
                "fredssträvandens", "fredssträvandena", "fredssträvandenas",
            },
            set(entry.forms if entry else ()),
        )

    def test_keeps_only_lemma_for_any_k_markup_in_source_text(self) -> None:
        for pattern in (
            "+t; pl. + H +<k>s</k>",
            "+en; gamla: former: <k>nåde</k> och: <k>nåder<",
            "+n <K>godtyckligt</K>",
        ):
            with self.subTest(pattern=pattern):
                entry = self.complete("testord", pattern)
                self.assertIsNotNone(entry)
                self.assertEqual(("testord",), entry.forms if entry else ())

    def test_unmarked_genitive_after_s_x_or_z(self) -> None:
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertIn("hus", set(entry.forms if entry else ()))
        self.assertNotIn("huss", set(entry.forms if entry else ()))

    def test_leaves_other_word_classes_unchanged(self) -> None:
        record = {
            "normaliserat_ord": "snabb",
            "upos": "ADJ",
            "ordkl": "adj.",
            "text": "+t +a",
        }
        initial = generate_entry(record)
        completed = complete_noun_entry(record, initial)
        self.assertEqual(initial, completed)


if __name__ == "__main__":
    unittest.main()
