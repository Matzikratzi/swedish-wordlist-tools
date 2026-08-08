from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounArticleScopeTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def assert_singular_only(self, lemma: str, pattern: str, expected_definite: str) -> None:
        entry = self.complete(lemma, pattern)
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertEqual(
            {lemma, lemma + "s", expected_definite, expected_definite + "s"},
            forms,
        )

    def test_hyperaktivitet_does_not_inherit_plural_from_aktivitet(self) -> None:
        # SAOL14: hyperaktivitet +en, while aktivitet itself has +en +er.
        self.assert_singular_only("hyperaktivitet", "+en", "hyperaktiviteten")

    def test_fostbrodraskap_does_not_inherit_zero_plural_from_brodraskap(self) -> None:
        # SAOL14: fostbrödraskap +et, while brödraskap itself has explicit plural.
        self.assert_singular_only("fostbrödraskap", "+et", "fostbrödraskapet")

    def test_ackordsarbete_does_not_inherit_n_plural_from_arbete(self) -> None:
        # SAOL14: ackordsarbete +t, while arbete itself has +t +n.
        self.assert_singular_only("ackordsarbete", "+t", "ackordsarbetet")

    def test_fackanslutning_does_not_inherit_ar_plural_from_anslutning(self) -> None:
        # SAOL14: fackanslutning +en, while anslutning itself has +en +ar.
        self.assert_singular_only("fackanslutning", "+en", "fackanslutningen")

    def test_plural_is_generated_when_the_article_itself_says_so(self) -> None:
        entry = self.complete("aktivitet", "+en +er")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("aktiviteter", forms)
        self.assertIn("aktiviteterna", forms)

        entry = self.complete("arbete", "+t +n")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertIn("arbeten", forms)
        self.assertIn("arbetena", forms)


if __name__ == "__main__":
    unittest.main()
