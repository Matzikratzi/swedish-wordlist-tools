from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_x_ambiguous import analyze, render_text


class AnalyzeXAmbiguousTests(unittest.TestCase):
    def test_reports_competing_headwords_and_generated_forms(self) -> None:
        noun = {
            "id": "n1", "normaliserat_ord": "beta", "homonr": "1",
            "ord": "beta", "stycke": "beta", "ordkl": "s. <i>+n +or</i>",
            "text": "+n +or", "upos": "NOUN",
        }
        verb = {
            "id": "v1", "normaliserat_ord": "beta", "homonr": "2",
            "ord": "beta", "stycke": "beta", "ordkl": "v. <i>+de +t</i>",
            "text": "+de +t", "upos": "VERB",
        }
        hv = {
            "id": "x1", "normaliserat_ord": "beta", "homonr": "0",
            "ord": "betaga", "stycke": "betaga", "ordkl": "(hv)",
            "text": None, "upos": "X",
        }
        report = analyze([noun, verb, hv])
        self.assertEqual(1, report["ambiguous_records"])
        case = report["cases"][0]
        self.assertEqual("betaga", case["printed_form"])
        self.assertEqual(["NOUN", "VERB"], case["candidate_classes"])
        by_upos = {candidate["upos"]: candidate for candidate in case["candidates"]}
        self.assertEqual("generated", by_upos["NOUN"]["generated_status"])
        self.assertEqual("generated", by_upos["VERB"]["generated_status"])
        self.assertIn("beta", by_upos["NOUN"]["generated_forms"])
        self.assertIn("betade", by_upos["VERB"]["generated_forms"])
        text = render_text(report)
        self.assertIn("FALL 01: beta -> 'betaga'", text)

    def test_pronoun_candidate_is_marked_when_case_is_truly_ambiguous(self) -> None:
        noun = {
            "normaliserat_ord": "en", "homonr": "5", "ord": "en",
            "ordkl": "s. <i>+en +ar</i>", "text": "+en +ar", "upos": "NOUN",
        }
        pron = {
            "normaliserat_ord": "en", "homonr": "3", "ord": "en",
            "ordkl": "pron. <i>gen. ens</i>", "text": "gen. ens", "upos": "PRON",
        }
        hv = {
            "normaliserat_ord": "en", "homonr": "0", "ord": "ett",
            "ordkl": "(hv)", "text": None, "upos": "X",
        }
        report = analyze([noun, pron, hv])
        self.assertEqual(1, report["ambiguous_records"])
        case = report["cases"][0]
        by_upos = {candidate["upos"]: candidate for candidate in case["candidates"]}
        self.assertEqual("no_shared_generator", by_upos["PRON"]["generated_status"])
        self.assertEqual([], by_upos["PRON"]["generated_forms"])

    def test_numbered_hv_variants_are_not_reported_as_ambiguous(self) -> None:
        adjective = {
            "normaliserat_ord": "karcinogen", "homonr": "1", "ord": "karcinogen",
            "ordkl": "adj. <i>+t +a</i>", "text": "+t +a", "upos": "ADJ",
        }
        noun = {
            "normaliserat_ord": "karcinogen", "homonr": "2", "ord": "karcinogen",
            "ordkl": "s. <i>+en +er</i>", "text": "+en +er", "upos": "NOUN",
        }
        hv = {
            "normaliserat_ord": "karcinogen", "homonr": "1", "ord": "carcinogen",
            "ordkl": "(hv)", "text": None, "upos": "X",
        }
        report = analyze([adjective, noun, hv])
        self.assertEqual(0, report["ambiguous_records"])


if __name__ == "__main__":
    unittest.main()
