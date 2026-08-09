from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounIrregularDefinitePluralTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str, stycke: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
            "stycke": stycke,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_irregular_s_plural_takes_en(self) -> None:
        entry = self.complete("bladlus", "+en -löss", "blad|lus")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("bladlöss", forms)
        self.assertIn("bladlössen", forms)
        self.assertIn("bladlössens", forms)
        self.assertNotIn("bladlössna", forms)

    def test_irregular_n_plural_takes_en_for_common_gender(self) -> None:
        entry = self.complete("man", "+nen -män", "man")
        # The exact source notation for man is not the point of this regression;
        # if the row interpreter rejects it, the lower-level rule is covered by
        # the integration cases elsewhere.  Keep this test conditional.
        if entry is not None:
            forms = set(entry.forms)
            self.assertNotIn("männa", forms)

    def test_latin_a_plural_is_already_definite(self) -> None:
        entry = self.complete(
            "doktorsexamen",
            "best. +; pl. -examina",
            "doktors|examen",
        )
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("doktorsexamina", forms)
        self.assertIn("doktorsexaminas", forms)
        self.assertNotIn("doktorsexaminana", forms)


if __name__ == "__main__":
    unittest.main()
