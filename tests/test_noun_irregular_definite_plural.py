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

    def test_sixth_declension_stem_change_takes_en(self) -> None:
        entry = self.complete("bladlus", "+en -löss", "blad|lus")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("bladlöss", forms)
        self.assertIn("bladlössen", forms)
        self.assertIn("bladlössens", forms)
        self.assertNotIn("bladlössna", forms)

    def test_latin_a_plural_takes_no_definiteness_suffix(self) -> None:
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

    def test_generic_s_plural_does_not_invent_definite_plural(self) -> None:
        entry = self.complete("gringo", "+n; pl. +s", "gringo")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("gringos", forms)
        self.assertNotIn("gringosen", forms)
        self.assertNotIn("gringosna", forms)

    def test_latin_i_plural_takes_no_definiteness_suffix(self) -> None:
        entry = self.complete("testum", "+et -testi", "testum")
        if entry is not None:
            forms = set(entry.forms)
            self.assertNotIn("testina", forms)
            self.assertNotIn("testien", forms)

    def test_common_gender_zero_plural_with_en_takes_en(self) -> None:
        # SAOL: pfennig ~en; pl. ~ -> pfennig, best. pl. pfennigen.
        entry = self.complete("pfennig", "+en; pl. +", "pfennig")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("pfennig", forms)
        self.assertIn("pfennigen", forms)
        self.assertIn("pfennigens", forms)
        self.assertNotIn("pfennigarna", forms)
        self.assertNotIn("pfennigena", forms)
        self.assertNotIn("pfennig na", forms)

    def test_common_gender_zero_plural_with_n_keeps_na_subtype(self) -> None:
        entry = self.complete("demo", "+n; pl. +", "demo")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("demo", forms)
        self.assertIn("demon", forms)
        self.assertIn("demona", forms)
        self.assertIn("demonas", forms)


if __name__ == "__main__":
    unittest.main()
