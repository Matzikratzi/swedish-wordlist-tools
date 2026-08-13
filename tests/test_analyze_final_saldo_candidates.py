from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_final_saldo_candidates import analyze, render


class AnalyzeFinalSaldoCandidatesTests(unittest.TestCase):
    def test_groups_by_category_upos_msd_and_saol_notation(self) -> None:
        rows = [{
            "form": "abdikerar",
            "primary_category": "CORE_INFLECTION",
            "matching_saol_articles": [{
                "upos": ["VERB"], "ordkl": "v. +de +t", "notation": "+de +t",
            }],
            "matching_saldo_analyses": [{
                "upos": "VERB", "msd": "pres ind aktiv", "lemmas": ["abdikera"],
            }],
        }, {
            "form": "abderitiskare",
            "primary_category": "COMPARISON",
            "matching_saol_articles": [{
                "upos": ["ADJ"], "ordkl": "adj. +t +a", "notation": "+t +a",
            }],
            "matching_saldo_analyses": [{
                "upos": "ADJ", "msd": "komp nom", "lemmas": ["abderitisk"],
            }],
        }]
        report = analyze(rows, examples_per_group=1)
        self.assertEqual(2, report["candidate_count"])
        self.assertEqual(1, report["categories"]["CORE_INFLECTION"])
        self.assertEqual(1, report["category_upos"][("CORE_INFLECTION", "VERB")])
        self.assertEqual(1, report["category_msd"][("COMPARISON", "komp nom")])
        self.assertEqual(1, report["category_notation"][("COMPARISON", "+t +a")])

        text = render(report)
        self.assertIn("CORE_INFLECTION", text)
        self.assertIn("notation='+de +t'", text)
        self.assertIn("'abderitiskare'", text)


if __name__ == "__main__":
    unittest.main()
