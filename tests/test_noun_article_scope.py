from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class NounArticleScopeTests(unittest.TestCase):
    def complete(self, lemma: str, pattern: str, stycke: str | None = None):
        record = {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        if stycke is not None:
            record["stycke"] = stycke
        return complete_noun_entry(record, generate_entry(record))

    def assert_singular_only(
        self,
        lemma: str,
        pattern: str,
        expected_definite: str,
        *,
        stycke: str | None = None,
    ) -> None:
        entry = self.complete(lemma, pattern, stycke)
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertEqual(
            {lemma, lemma + "s", expected_definite, expected_definite + "s"},
            forms,
        )

    def test_hyperaktivitet_does_not_inherit_plural_from_aktivitet(self) -> None:
        # SAOL14: hyperaktivitet +en, while aktivitet itself has +en +er.
        self.assert_singular_only(
            "hyperaktivitet", "+en", "hyperaktiviteten", stycke="hyper|akt·iv·itet"
        )

    def test_fostbrodraskap_does_not_inherit_zero_plural_from_brodraskap(self) -> None:
        # SAOL14: fostbrödraskap +et, while brödraskap itself has explicit plural.
        self.assert_singular_only(
            "fostbrödraskap", "+et", "fostbrödraskapet", stycke="fost|brödra·skap"
        )

    def test_ackordsarbete_does_not_inherit_n_plural_from_arbete(self) -> None:
        # SAOL14: ackordsarbete +t, while arbete itself has +t +n.
        self.assert_singular_only(
            "ackordsarbete", "+t", "ackordsarbetet", stycke="ac·kords|arbete"
        )

    def test_fackanslutning_does_not_inherit_ar_plural_from_anslutning(self) -> None:
        # SAOL14: fackanslutning +en, while anslutning itself has +en +ar.
        self.assert_singular_only(
            "fackanslutning", "+en", "fackanslutningen", stycke="fack|an·slut·ning"
        )

    def test_honsarv_does_not_inherit_gender_or_plural_from_arv(self) -> None:
        # SAOL14: höns|arv +en, while the independent article arv has +et; pl. +.
        # The compound article controls both definite singular and paradigm scope.
        entry = self.complete("hönsarv", "+en", "höns|arv")
        self.assertIsNotNone(entry)
        forms = set(entry.forms if entry else ())
        self.assertEqual({"hönsarv", "hönsarvs", "hönsarven", "hönsarvens"}, forms)
        self.assertNotIn("hönsarvet", forms)
        self.assertNotIn("hönsarvets", forms)

    def test_bar_is_word_structure_not_paradigm_inheritance(self) -> None:
        # A printed compound boundary may guide stem operations, but it must not
        # trigger lookup or completion from the right-hand tail.
        with_bar = self.complete("fackanslutning", "+en", "fack|an·slut·ning")
        without_bar = self.complete("fackanslutning", "+en")
        self.assertIsNotNone(with_bar)
        self.assertIsNotNone(without_bar)
        self.assertEqual(
            set(with_bar.forms if with_bar else ()),
            set(without_bar.forms if without_bar else ()),
        )

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
