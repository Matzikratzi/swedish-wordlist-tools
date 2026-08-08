import unittest

from swedish_wordlist_tools.analyze_article_scope_validation_status import analyze


class ArticleScopeValidationStatusTests(unittest.TestCase):
    def test_counts_subset_status_for_saldo_plural_completion(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "kyrkofrid",
            "notation": "+en",
            "generated_forms": ["kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens"],
            "saldo_forms": [
                "kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens",
                "kyrkofrider", "kyrkofriders", "kyrkofriderna", "kyrkofridernas",
            ],
            "status": "saol_forms_are_subset",
            "semantic_status": "saol_forms_are_subset",
        }]
        summary = analyze(rows)
        self.assertEqual(1, summary["records"])
        self.assertEqual({"saol_forms_are_subset": 1}, summary["status_counts"])

    def test_ignores_explicit_plural_notation(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "aktivitet",
            "notation": "+en +er",
            "generated_forms": ["aktivitet", "aktiviteten", "aktiviteter"],
            "saldo_forms": ["aktivitet", "aktiviteten", "aktiviteter", "aktiviteterna"],
            "status": "saol_forms_are_subset",
        }]
        self.assertEqual(0, analyze(rows)["records"])


if __name__ == "__main__":
    unittest.main()
