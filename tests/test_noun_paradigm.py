from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
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
        self.assertEqual({"mjölk", "mjölks", "mjölken", "mjölkens"}, set(entry.forms if entry else ()))

    def test_completes_n_singular_only_noun(self) -> None:
        entry = self.complete("afasi", "+n")
        self.assertIsNotNone(entry)
        self.assertEqual({"afasi", "afasis", "afasin", "afasins"}, set(entry.forms if entry else ()))

    def test_completes_et_singular_only_noun(self) -> None:
        entry = self.complete("ansvar", "+et")
        self.assertIsNotNone(entry)
        self.assertEqual({"ansvar", "ansvars", "ansvaret", "ansvarets"}, set(entry.forms if entry else ()))

    def test_completes_t_singular_only_noun(self) -> None:
        entry = self.complete("foto", "+t")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"foto", "fotos", "fotot", "fotots"},
            set(entry.forms if entry else ()),
        )

    def test_unmarked_genitive_after_s_x_or_z(self) -> None:
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertIn("hus", set(entry.forms if entry else ()))
        self.assertNotIn("huss", set(entry.forms if entry else ()))

    def test_leaves_other_word_classes_unchanged(self) -> None:
        record = {"normaliserat_ord": "snabb", "upos": "ADJ", "ordkl": "adj.", "text": "+t +a"}
        initial = generate_entry(record)
        completed = complete_noun_entry(record, initial)
        self.assertEqual(initial, completed)


if __name__ == "__main__":
    unittest.main()
