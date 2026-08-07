from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_heading_format import analyze, classify_reference, parse_heading
from swedish_wordlist_tools.saol_article_headings import is_plain_reference, materialize_heading_model


class AnalyzeSaolHeadingFormatTests(unittest.TestCase):
    def test_parse_heading_extracts_superscript_homonym(self) -> None:
        parsed = parse_heading("<sup>4</sup>abs·trakt")
        self.assertEqual("4", parsed["explicit_homonym"])
        self.assertEqual("abs·trakt", parsed["without_sup"])
        self.assertEqual("abstrakt", parsed["lexical"])

    def test_superscript_is_checked_against_homonr(self) -> None:
        rows = [
            {
                "normaliserat_ord": "abstrakt",
                "homonr": "4",
                "ord": "<sup>4</sup>abs·trakt",
                "stycke": "<sup>4</sup>abs·trakt",
                "ordkl": "s.",
            },
            {
                "normaliserat_ord": "x",
                "homonr": "2",
                "ord": "<sup>3</sup>x",
                "stycke": "<sup>3</sup>x",
                "ordkl": "s.",
            },
        ]
        _, summary = analyze(rows)
        self.assertEqual(2, summary["rows_with_explicit_superscript_homonym"])
        self.assertEqual(1, summary["explicit_superscript_homonr_mismatches"])

    def test_annotated_hv_is_reference_and_inflection_is_classified(self) -> None:
        row = {
            "normaliserat_ord": "få",
            "homonr": "0",
            "ord": "färre",
            "stycke": "färre",
            "ordkl": "(hv) <i>komp.</i>",
            "text": "komp.",
        }
        self.assertTrue(is_plain_reference(row))
        self.assertEqual("inflection_reference", classify_reference(row))
        model = materialize_heading_model([row])
        self.assertEqual([], model["articles"])
        self.assertEqual(1, len(model["references"]))
        self.assertEqual([], model["unresolved"])

    def test_plain_hv_remains_plain_reference(self) -> None:
        row = {
            "normaliserat_ord": "akne",
            "homonr": "1",
            "ord": "acne",
            "stycke": "acne",
            "ordkl": "(hv)",
        }
        self.assertEqual("plain_reference", classify_reference(row))


if __name__ == "__main__":
    unittest.main()
