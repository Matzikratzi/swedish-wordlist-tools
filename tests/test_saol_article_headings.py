from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_article_headings import materialize_heading_model


class SaolArticleHeadingsTests(unittest.TestCase):
    def test_materializes_alternate_heading_without_losing_homonym(self) -> None:
        rows = [
            {
                "normaliserat_ord": "akne",
                "homonr": "1",
                "ordkl": "s. <i>+n</i>",
                "urspr_lopnr": 438305,
                "subnr": 438305,
                "ord": "akne",
            },
            {
                "normaliserat_ord": "akne",
                "homonr": "0",
                "ordkl": "s. <i>+n</i>",
                "urspr_lopnr": 438305,
                "subnr": 438305,
                "ord": "acne",
            },
        ]
        model = materialize_heading_model(rows)
        self.assertEqual(1, len(model["articles"]))
        article = model["articles"][0]
        self.assertEqual("1", article["homonym_number"])
        self.assertEqual(["akne"], article["primary_headings"])
        self.assertEqual(["acne"], article["alternate_headings"])
        self.assertEqual([], model["references"])

    def test_plain_hv_is_reference_even_with_homonr_one(self) -> None:
        rows = [
            {
                "normaliserat_ord": "akne",
                "homonr": "1",
                "ordkl": "(hv)",
                "urspr_lopnr": 436676,
                "subnr": 436676,
                "ord": "acne",
                "upos": "X",
            }
        ]
        model = materialize_heading_model(rows)
        self.assertEqual([], model["articles"])
        self.assertEqual(1, len(model["references"]))
        self.assertEqual("acne", model["references"][0]["heading"])
        self.assertEqual("akne", model["references"][0]["target_normalised_word"])
        self.assertEqual("1", model["references"][0]["source_homonr"])

    def test_alternate_heading_is_attached_to_homonym_two(self) -> None:
        rows = [
            {
                "normaliserat_ord": "amarant",
                "homonr": "2",
                "ordkl": "s. <i>+en</i>",
                "urspr_lopnr": 440792,
                "subnr": 440792,
                "ord": "<sup>2</sup>amar·ant",
            },
            {
                "normaliserat_ord": "amarant",
                "homonr": "0",
                "ordkl": "s. <i>+en</i>",
                "urspr_lopnr": 440792,
                "subnr": 440792,
                "ord": "Amar·ant",
            },
        ]
        model = materialize_heading_model(rows)
        self.assertEqual(1, len(model["articles"]))
        self.assertEqual("2", model["articles"][0]["homonym_number"])
        self.assertEqual(["Amar·ant"], model["articles"][0]["alternate_headings"])

    def test_ambiguous_zero_with_multiple_nonzero_homonyms_is_not_guessed(self) -> None:
        rows = [
            {"normaliserat_ord": "x", "homonr": "1", "ordkl": "s.", "urspr_lopnr": 10, "subnr": 10, "ord": "x1"},
            {"normaliserat_ord": "x", "homonr": "2", "ordkl": "s.", "urspr_lopnr": 10, "subnr": 10, "ord": "x2"},
            {"normaliserat_ord": "x", "homonr": "0", "ordkl": "s.", "urspr_lopnr": 10, "subnr": 10, "ord": "xa"},
        ]
        model = materialize_heading_model(rows)
        self.assertEqual(2, len(model["articles"]))
        self.assertTrue(all(not article["alternate_headings"] for article in model["articles"]))
        self.assertEqual("ambiguous_zero_heading_anchor", model["unresolved"][0]["kind"])


if __name__ == "__main__":
    unittest.main()
