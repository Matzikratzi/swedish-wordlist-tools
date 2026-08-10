from __future__ import annotations

import unittest

from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounHomonymStyckeReplacementTests(unittest.TestCase):
    def _forms(self, lemma: str, text: str, stycke: str) -> set[str]:
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "s.",
            "text": text,
            "stycke": stycke,
        }
        entry = complete_noun_entry(record, None)
        self.assertIsNotNone(entry)
        assert entry is not None
        return set(entry.forms)

    def test_plain_homonym_number_does_not_hide_compound_bar(self) -> None:
        forms = self._forms("flåhacka", "+n -hackor", "1flå|hacka")
        self.assertTrue(
            {
                "flåhacka",
                "flåhackas",
                "flåhackan",
                "flåhackans",
                "flåhackor",
                "flåhackors",
                "flåhackorna",
                "flåhackornas",
            }.issubset(forms)
        )

    def test_sup_homonym_number_does_not_hide_compound_bar(self) -> None:
        forms = self._forms("avresa", "+n -resor", "<sup>1</sup>av|resa")
        self.assertTrue(
            {
                "avresa",
                "avresas",
                "avresan",
                "avresans",
                "avresor",
                "avresors",
                "avresorna",
                "avresornas",
            }.issubset(forms)
        )

    def test_same_structure_is_not_suffix_specific(self) -> None:
        examples = (
            ("frilista", "+n -listor", "1fri|lista", "frilistor"),
            ("halländska", "+n -ländskor", "1hal|ländska", "halländskor"),
            ("flåhacka", "+n -hackor", "1flå|hacka", "flåhackor"),
        )
        for lemma, text, stycke, plural in examples:
            with self.subTest(lemma=lemma):
                self.assertIn(plural, self._forms(lemma, text, stycke))


if __name__ == "__main__":
    unittest.main()
