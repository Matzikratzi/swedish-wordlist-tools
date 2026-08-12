from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_x_unresolved import analyze, render_text


class AnalyzeXUnresolvedTests(unittest.TestCase):
    def test_reports_nonshared_sibling_instead_of_calling_it_headless(self) -> None:
        propn = {
            "id": "p1",
            "normaliserat_ord": "Budda",
            "homonr": "1",
            "ord": "Budda",
            "stycke": "Budda",
            "ordkl": "namn",
            "text": None,
            "upos": "PROPN",
        }
        hv = {
            "id": "x1",
            "normaliserat_ord": "Budda",
            "homonr": "1",
            "ord": "Buddha",
            "stycke": "Buddha",
            "ordkl": "(hv)",
            "text": None,
            "upos": "X",
        }
        report = analyze([propn, hv])
        self.assertEqual(1, report["unresolved_records"])
        case = report["cases"][0]
        self.assertEqual("nonshared_sibling", case["shape"])
        self.assertEqual(["PROPN"], case["non_x_classes"])
        self.assertEqual("Buddha", case["printed_form"])

    def test_distinguishes_variant_without_non_x_sibling(self) -> None:
        hv = {
            "normaliserat_ord": "in absurdum",
            "ord": "absurdum",
            "ordkl": "(hv)",
            "text": None,
            "upos": "X",
        }
        report = analyze([hv])
        self.assertEqual(1, report["unresolved_records"])
        self.assertEqual("variant_without_non_x_sibling", report["cases"][0]["shape"])

    def test_render_contains_summary_and_candidate_details(self) -> None:
        interj = {
            "normaliserat_ord": "brr",
            "ord": "brr",
            "homonr": "2",
            "ordkl": "interj.",
            "text": None,
            "upos": "INTJ",
        }
        hv = {
            "normaliserat_ord": "brr",
            "ord": "burr",
            "homonr": "2",
            "ordkl": "(hv)",
            "text": None,
            "upos": "X",
        }
        text = render_text(analyze([interj, hv]))
        self.assertIn("Olösta poster: 1", text)
        self.assertIn("INTJ", text)
        self.assertIn("brr -> 'burr'", text)


if __name__ == "__main__":
    unittest.main()
