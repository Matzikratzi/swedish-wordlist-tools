import unittest

from swedish_wordlist_tools.analyze_article_scope_mismatch_impact import candidates


class ArticleScopeMismatchImpactTests(unittest.TestCase):
    def test_finds_unclassified_singular_only_with_only_saldo_plural(self):
        rows = [{
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "hyperaktivitet",
            "homonym_number": "1",
            "record_id": "1",
            "notation": "+en",
            "extra_from_saol": [],
            "missing_from_saol": [
                "hyperaktiviteter", "hyperaktiviteterna",
                "hyperaktiviteternas", "hyperaktiviteters",
            ],
        }]
        result = candidates(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("hyperaktivitet", result[0]["lemma"])

    def test_ignores_when_saol_has_extra_forms_too(self):
        rows = [{
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "x",
            "notation": "+en",
            "extra_from_saol": ["xen"],
            "missing_from_saol": ["xer"],
        }]
        self.assertEqual([], candidates(rows))

    def test_ignores_explicit_plural_article(self):
        rows = [{
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "aktivitet",
            "notation": "+en +er",
            "extra_from_saol": [],
            "missing_from_saol": ["aktiviteter"],
        }]
        self.assertEqual([], candidates(rows))


if __name__ == "__main__":
    unittest.main()
