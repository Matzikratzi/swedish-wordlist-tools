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

    def test_hv_form_resolves_homonymous_verb_and_adjective(self) -> None:
        verb = {
            "normaliserat_ord": "få", "ord": "få", "homonr": "1", "upos": "VERB",
            "ordkl": "v.", "text": "fick konjunktiv: finge, fått, pres. får",
        }
        adjective = {
            "normaliserat_ord": "få", "ord": "få", "homonr": "2", "upos": "ADJ",
            "ordkl": "adj.", "text": "komp. färre, superl. färst",
        }
        fick = {
            "normaliserat_ord": "få", "ord": "fick", "homonr": "0", "upos": "X",
            "ordkl": "(hv)", "text": None,
        }
        farst = {
            "normaliserat_ord": "få", "ord": "färst", "homonr": "0", "upos": "X",
            "ordkl": "(hv)", "text": None,
        }
        siblings = {"få": [verb, adjective, fick, farst]}

        route, evidence = classify_x_record(fick, siblings)
        self.assertEqual("route_VERB_shared_from_hv_sibling_form", route)
        self.assertEqual(("VERB",), evidence)

        route, evidence = classify_x_record(farst, siblings)
        self.assertEqual("route_ADJ_shared_from_hv_sibling_form", route)
        self.assertEqual(("ADJ",), evidence)

    def test_hv_form_stays_ambiguous_when_both_homonyms_print_it(self) -> None:
        noun = {
            "normaliserat_ord": "x", "ord": "x", "upos": "NOUN",
            "ordkl": "subst.", "text": "same",
        }
        adjective = {
            "normaliserat_ord": "x", "ord": "x", "upos": "ADJ",
            "ordkl": "adj.", "text": "same",
        }
        hv = {
            "normaliserat_ord": "x", "ord": "same", "upos": "X",
            "ordkl": "(hv)", "text": None,
        }
        route, evidence = classify_x_record(hv, {"x": [noun, adjective, hv]})
        self.assertEqual("ambiguous_hv_sibling_classes", route)
        self.assertEqual(("ADJ", "NOUN"), evidence)

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
        self.assertEqual(3, report["x_routing_records"])
        self.assertEqual(0, report["x_hv_records_without_text"])
        self.assertEqual(1, report["route_counts"]["remaining_ADV"])
        self.assertEqual(1, report["route_counts"]["remaining_NUM"])
        self.assertEqual(1, report["route_counts"]["remaining_ARTICLE"])

    def test_report_includes_hv_rows_without_text(self) -> None:
        verb = {
            "normaliserat_ord": "få", "ord": "få", "upos": "VERB",
            "ordkl": "v.", "text": "fick fått får",
        }
        adjective = {
            "normaliserat_ord": "få", "ord": "få", "upos": "ADJ",
            "ordkl": "adj.", "text": "färre färst",
        }
        fick = {
            "normaliserat_ord": "få", "ord": "fick", "upos": "X",
            "ordkl": "(hv)", "text": None,
        }
        report = analyze([verb, adjective, fick])
        self.assertEqual(0, report["x_text_records"])
        self.assertEqual(1, report["x_hv_records_without_text"])
        self.assertEqual(1, report["x_routing_records"])
        self.assertEqual(1, report["route_counts"]["route_VERB_shared_from_hv_sibling_form"])


if __name__ == "__main__":
    unittest.main()
