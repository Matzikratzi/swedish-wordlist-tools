import unittest

from swedish_wordlist_tools.analyze_surface_lemma_variants import analyze


class AnalyzeSurfaceLemmaVariantsTests(unittest.TestCase):
    def test_reports_acne_as_written_variant_of_normalized_akne(self):
        summary = analyze([
            {
                "normaliserat_ord": "akne",
                "ord": "acne",
                "homonr": "0",
                "subnr": 1,
                "upos": "NOUN",
                "ordkl": "s. +n",
                "text": "+n",
            }
        ])
        self.assertEqual(1, summary["records"])
        row = summary["rows"][0]
        self.assertEqual("akne", row["normaliserat_ord"])
        self.assertEqual("acne", row["ord"])
        self.assertEqual("different_spelling", row["kind"])

    def test_presentation_marks_do_not_create_false_difference(self):
        summary = analyze([
            {
                "normaliserat_ord": "aknebehandling",
                "ord": "akne|be·handl·ing",
                "upos": "NOUN",
                "ordkl": "s. +en +ar",
                "text": "+en +ar",
            }
        ])
        self.assertEqual(0, summary["records"])

    def test_spaces_and_hyphens_are_preserved(self):
        summary = analyze([
            {
                "normaliserat_ord": "a conto-betalning",
                "ord": "a conto-be·taln·ing",
                "upos": "NOUN",
                "ordkl": "s. +en +ar",
                "text": "+en +ar",
            }
        ])
        self.assertEqual(0, summary["records"])


if __name__ == "__main__":
    unittest.main()
