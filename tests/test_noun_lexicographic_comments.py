from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounLexicographicCommentTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_completes_compound_ansokan_plural(self) -> None:
        entry = self.complete(
            "avskedsansökan",
            "best. +; i: pl. används: -ansökningar",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "avskedsansökan",
                "avskedsansökans",
                "avskedsansökningar",
                "avskedsansökningars",
                "avskedsansökningarna",
                "avskedsansökningarnas",
            },
            set(entry.forms if entry else ()),
        )

    def test_completes_compound_verkan_plural(self) -> None:
        entry = self.complete(
            "biverkan",
            "best. +; i: pl. används: -verkningar",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "biverkan",
                "biverkans",
                "biverkningar",
                "biverkningars",
                "biverkningarna",
                "biverkningarnas",
            },
            set(entry.forms if entry else ()),
        )

    def test_completes_officer_plural_comment(self) -> None:
        entry = self.complete(
            "dagofficer",
            "+en; som: pl. anv. +are, best. pl. +arna",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "dagofficer",
                "dagofficers",
                "dagofficeren",
                "dagofficerens",
                "dagofficerare",
                "dagofficerares",
                "dagofficerarna",
                "dagofficerarnas",
            },
            set(entry.forms if entry else ()),
        )


if __name__ == "__main__":
    unittest.main()
