import unittest

from swedish_wordlist_tools.noun_paradigm import complete_noun_entry
from swedish_wordlist_tools.saol_surface import clean_saol_word, surface_lemma


class SaolSurfaceVariantTests(unittest.TestCase):
    def test_cleans_presentation_separators_from_ord(self):
        self.assertEqual("aknebehandling", clean_saol_word("akne|be·handl·ing"))
        self.assertEqual("ackvisitör", clean_saol_word("ac·kvis·it·ör"))

    def test_preserves_real_spaces_and_hyphens(self):
        self.assertEqual(
            "a conto-betalning",
            clean_saol_word("a conto-be·taln·ing"),
        )
        self.assertEqual(
            "a conto-betalning",
            clean_saol_word("a conto-|be·taln·ing"),
        )

    def test_surface_value_is_diagnostic_but_does_not_globally_replace_lemma(self):
        record = {
            "normaliserat_ord": "akne",
            "ord": "acne",
            "upos": "NOUN",
            "ordkl": "s. +n",
            "stycke": "akne",
            "text": "+n",
        }
        # ``ord`` exposes an important alternative written form, but it is not
        # safe to use globally as the paradigm base: other rows use ``ord`` for
        # phrase-bound forms such as ``ankar`` under ``ankare``.
        self.assertEqual("acne", surface_lemma(record))
        entry = complete_noun_entry(record, None)
        self.assertIsNotNone(entry)
        self.assertEqual("akne", entry.lemma if entry else None)
        self.assertEqual(
            {"akne", "aknes", "aknen", "aknens"},
            set(entry.forms if entry else ()),
        )

    def test_ord_ankar_does_not_replace_ankare_as_paradigm_base(self):
        record = {
            "normaliserat_ord": "ankare",
            "ord": "ankar",
            "upos": "NOUN",
            "ordkl": "s.",
            "stycke": "ankare",
            "text": "+t",
        }
        entry = complete_noun_entry(record, None)
        self.assertIsNotNone(entry)
        self.assertEqual("ankare", entry.lemma if entry else None)
        self.assertIn("ankare", set(entry.forms if entry else ()))
        self.assertNotIn("ankar", set(entry.forms if entry else ()))

    def test_normalized_akne_row_keeps_akne_family(self):
        record = {
            "normaliserat_ord": "akne",
            "ord": "akne",
            "upos": "NOUN",
            "ordkl": "s. +n",
            "stycke": "akne",
            "text": "+n",
        }
        entry = complete_noun_entry(record, None)
        self.assertIsNotNone(entry)
        self.assertEqual(
            {"akne", "aknes", "aknen", "aknens"},
            set(entry.forms if entry else ()),
        )


if __name__ == "__main__":
    unittest.main()
