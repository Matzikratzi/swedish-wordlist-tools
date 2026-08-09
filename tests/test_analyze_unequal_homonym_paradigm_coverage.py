import unittest

from swedish_wordlist_tools.analyze_unequal_homonym_paradigm_coverage import compare_one


class UnequalHomonymParadigmCoverageTests(unittest.TestCase):
    def test_exact_match(self):
        saol = {"homonym_number": "1", "generated_forms": ["duns", "dunset"]}
        saldo = {"id": "x", "forms": ["duns", "dunset"]}
        result = compare_one(saol, saldo)
        self.assertTrue(result["exact"])
        self.assertTrue(result["saol_subset"])

    def test_subset_match(self):
        saol = {"homonym_number": "1", "generated_forms": ["duns", "dunset"]}
        saldo = {"id": "x", "forms": ["duns", "dunset", "dunsen"]}
        result = compare_one(saol, saldo)
        self.assertFalse(result["exact"])
        self.assertTrue(result["saol_subset"])

    def test_conflict(self):
        saol = {"homonym_number": "2", "generated_forms": ["duns", "dunset"]}
        saldo = {"id": "x", "forms": ["duns", "dunsen"]}
        result = compare_one(saol, saldo)
        self.assertFalse(result["exact"])
        self.assertFalse(result["saol_subset"])
        self.assertEqual(["dunset"], result["saol_only"])


if __name__ == "__main__":
    unittest.main()
