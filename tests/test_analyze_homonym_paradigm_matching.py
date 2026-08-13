import unittest

from swedish_wordlist_tools.analyze_homonym_paradigm_matching import best_assignment, pair_score


class HomonymParadigmMatchingTests(unittest.TestCase):
    def test_exact_pair_beats_partial_pair(self):
        saol = {"generated_forms": ["fot", "foten", "fötter"]}
        exact = {"forms": ["fot", "foten", "fötter"]}
        partial = {"forms": ["fot", "fotet", "fötter"]}
        self.assertGreater(pair_score(saol, exact), pair_score(saol, partial))

    def test_global_assignment_swaps_analyses(self):
        saol = [
            {"homonym_number": "1", "generated_forms": ["ark", "arken", "arkar"]},
            {"homonym_number": "2", "generated_forms": ["ark", "arket", "ark"]},
        ]
        saldo = [
            {"id": "saldo-neuter", "forms": ["ark", "arket", "ark"]},
            {"id": "saldo-common", "forms": ["ark", "arken", "arkar"]},
        ]
        result = best_assignment(saol, saldo)
        self.assertEqual(1, result["tie_count"])
        self.assertEqual("saldo-common", result["pairs"][0]["saldo_id"])
        self.assertEqual("saldo-neuter", result["pairs"][1]["saldo_id"])
        self.assertTrue(all(pair["exact"] for pair in result["pairs"]))

    def test_reports_ambiguous_assignment(self):
        saol = [
            {"homonym_number": "1", "generated_forms": ["x", "xs"]},
            {"homonym_number": "2", "generated_forms": ["x", "xs"]},
        ]
        saldo = [
            {"id": "a", "forms": ["x", "xs"]},
            {"id": "b", "forms": ["x", "xs"]},
        ]
        result = best_assignment(saol, saldo)
        self.assertEqual(2, result["tie_count"])


if __name__ == "__main__":
    unittest.main()
