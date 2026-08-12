from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_x_routing import analyze, classify_x_record


class AnalyzeXRoutingTests(unittest.TestCase):
    def test_hv_routes_only_with_concrete_shared_sibling(self) -> None:
        hv = {
            "normaliserat_ord": "annektion", "ord": "annektion", "upos": "X",
            "ordkl": "(hv) <i>+en +er</i>", "text": "+en +er",
        }
        noun = {
            "normaliserat_ord": "annektion", "ord": "annektion", "upos": "NOUN",
            "ordkl": "subst.", "text": "+en +er",
        }
        route, evidence = classify_x_record(hv, {"annektion": [hv, noun]})
        self.assertEqual("route_NOUN_shared_from_hv_sibling", route)
        self.assertEqual(("NOUN",), evidence)

    def test_hv_without_shared_sibling_is_not_guessed(self) -> None:
        hv = {
            "normaliserat_ord": "x", "ord": "x", "upos": "X",
            "ordkl": "(hv) <i>+t +a</i>", "text": "+t +a",
        }
        route, evidence = classify_x_record(hv, {"x": [hv]})
        self.assertEqual("unresolved_hv_no_shared_sibling", route)
        self.assertEqual((), evidence)

    def test_mixed_adv_adj_routes_inflection_to_adjective_shared(self) -> None:
        record = {
            "normaliserat_ord": "ansatsvis", "ord": "ansatsvis", "upos": "X",
            "ordkl": "adv. och adj. <i>+t +a</i>", "text": "+t +a",
        }
        route, _ = classify_x_record(record, {"ansatsvis": [record]})
        self.assertEqual("route_ADJ_shared_from_mixed_adv_adj", route)

    def test_report_separates_adv_num_and_article(self) -> None:
        records = [
            {"normaliserat_ord": "bra", "ord": "bra", "upos": "X", "ordkl": "adv. <i>bättre bäst</i>", "text": "bättre bäst"},
            {"normaliserat_ord": "en", "ord": "en", "upos": "X", "ordkl": "räkn. <i>n. ett</i>", "text": "n. ett"},
            {"normaliserat_ord": "den", "ord": "den", "upos": "X", "ordkl": "best. artikel <i>n. det</i>", "text": "n. det"},
        ]
        report = analyze(records)
        self.assertEqual(3, report["x_text_records"])
        self.assertEqual(1, report["route_counts"]["remaining_ADV"])
        self.assertEqual(1, report["route_counts"]["remaining_NUM"])
        self.assertEqual(1, report["route_counts"]["remaining_ARTICLE"])


if __name__ == "__main__":
    unittest.main()
