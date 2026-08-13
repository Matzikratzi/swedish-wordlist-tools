import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class BareZeroPluralCompletionTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_bare_pl_plus_does_not_invent_definite_plural(self):
        entry = self.complete("ångström", "pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"ångström", "ångströms"},
            set(entry.forms if entry else ()),
        )
        self.assertNotIn("ångströmna", set(entry.forms if entry else ()))
        self.assertNotIn("ångströmnas", set(entry.forms if entry else ()))

    def test_neuter_zero_plural_still_derives_definite_plural(self):
        entry = self.complete("hus", "+et; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"hus", "huset", "husets", "husen", "husens"},
            set(entry.forms if entry else ()),
        )

    def test_common_gender_zero_plural_still_derives_definite_plural(self):
        entry = self.complete("demo", "+n; pl. +")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"demo", "demos", "demon", "demons", "demona", "demonas"},
            set(entry.forms if entry else ()),
        )


if __name__ == "__main__":
    unittest.main()
