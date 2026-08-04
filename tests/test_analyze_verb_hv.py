from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_hv import build_report, classify_missing_reference


class AnalyzeVerbHvTests(unittest.TestCase):
    def write_records(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".jsonl", delete=False
        )
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_matches_hv_form_to_generated_verb_form(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "glädjas", "homonr": "1", "ordkl": "v.",
                "upos": "VERB", "text": "gladdes, glatts, pres. gläds, imper. gläds",
                "stycke": "glädjas", "ord": "glädjas",
            },
            {
                "normaliserat_ord": "glädjas", "homonr": "0", "ordkl": "(hv)",
                "upos": "X", "text": "(null)", "stycke": "gladdes", "ord": "gladdes",
            },
        ])
        report = build_report(path)
        self.assertEqual(1, report["verb_targeted_hv_records"])
        self.assertEqual(1, report["matched_generated_verb_forms"])
        self.assertEqual(100.0, report["coverage_percent"])
        self.assertEqual("matched_generated_verb_form", report["records"][0]["status"])

    def test_strips_homonym_superscript_from_referred_form(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "ge", "homonr": "1", "ordkl": "v.",
                "upos": "VERB", "text": "gav, gett", "stycke": "ge", "ord": "ge",
            },
            {
                "normaliserat_ord": "ge", "homonr": "1", "ordkl": "(hv)",
                "upos": "X", "text": "(null)",
                "stycke": "<sup>1</sup>giva", "ord": "<sup>1</sup>giva",
            },
        ])
        row = build_report(path)["records"][0]
        self.assertEqual("giva", row["form"])
        self.assertEqual("1", row["target_homonr"])
        self.assertEqual("historic_infinitive", row["classification"])

    def test_reports_possible_inflection_without_adding_it(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "testa", "homonr": "1", "ordkl": "v.",
                "upos": "VERB", "text": "+de +t", "stycke": "testa", "ord": "testa",
            },
            {
                "normaliserat_ord": "testa", "homonr": "0", "ordkl": "(hv)",
                "upos": "X", "text": "(null)", "stycke": "testades", "ord": "testades",
            },
        ])
        report = build_report(path)
        row = report["records"][0]
        self.assertEqual("possible_inflection", row["classification"])
        self.assertEqual(1, report["possible_parser_misses"])
        self.assertNotIn("testades", row["generated_forms"])

    def test_ignores_hv_targeting_nonverb_lemma(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "akne", "homonr": "1", "ordkl": "(hv)",
                "upos": "X", "text": "(null)", "stycke": "acne", "ord": "acne",
            }
        ])
        self.assertEqual(0, build_report(path)["verb_targeted_hv_records"])

    def test_classifies_known_subjunctive(self) -> None:
        self.assertEqual(
            ("subjunctive", "known_subjunctive_form"),
            classify_missing_reference("ginge", "gå"),
        )

    def test_classifies_historic_infinitive(self) -> None:
        self.assertEqual(
            ("historic_infinitive", "historic_long_infinitive_pattern"),
            classify_missing_reference("giva", "ge"),
        )

    def test_classifies_alternative_spelling(self) -> None:
        self.assertEqual(
            ("alternative_spelling", "infinitive_like_reference_close_to_target"),
            classify_missing_reference("scanna", "skanna"),
        )

    def test_classifies_nonverbal_reference(self) -> None:
        self.assertEqual(
            ("nonverbal_reference", "reference_is_not_a_verb_form_in_this_use"),
            classify_missing_reference("närmast", "nära"),
        )

    def test_classifies_other_historic_reference(self) -> None:
        self.assertEqual(
            ("other_historic_reference", "known_historic_or_formulaic_reference"),
            classify_missing_reference("färst", "få"),
        )

    def test_leaves_uncertain_reference_unclassified(self) -> None:
        self.assertEqual(
            ("unclassified", "no_conservative_rule_matched"),
            classify_missing_reference("xyz", "testa"),
        )


if __name__ == "__main__":
    unittest.main()
