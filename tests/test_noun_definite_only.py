from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounDefiniteOnlyTests(unittest.TestCase):
    def test_best_label_uses_headword_as_definite_singular(self) -> None:
        record = {
            "normaliserat_ord": "kröken",
            "upos": "NOUN",
            "ordkl": "subst.; best.",
            "text": None,
            "stycke": "krök·en",
        }
        entry = complete_noun_entry(record, generate_entry(record))
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertEqual({"kröken", "krökens"}, forms)

    def test_best_plural_label_is_not_misread_as_singular_definite(self) -> None:
        record = {
            "normaliserat_ord": "test",
            "upos": "NOUN",
            "ordkl": "subst.; best. pl.",
            "text": None,
        }
        entry = complete_noun_entry(record, generate_entry(record))
        self.assertIsNone(entry)


if __name__ == "__main__":
    unittest.main()
