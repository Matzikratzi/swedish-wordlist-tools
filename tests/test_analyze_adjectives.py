from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_adjectives import build_report


class AnalyzeAdjectivesTests(unittest.TestCase):
    def write_records(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_counts_only_adjectives_and_null_text(self) -> None:
        path = self.write_records([
            {"normaliserat_ord": "glad", "upos": "ADJ", "text": "+are +ast", "stycke": "glad"},
            {"normaliserat_ord": "kort", "upos": "ADJ", "text": "(null)", "stycke": "kort"},
            {"normaliserat_ord": "springa", "upos": "VERB", "text": "sprang", "stycke": "springa"},
        ])
        report = build_report(path)
        self.assertEqual(2, report["adjective_records"])
        self.assertEqual(1, report["with_text"])
        self.assertEqual(1, report["without_text"])

    def test_marks_hard_cap_and_bar(self) -> None:
        text = "x" * 50
        path = self.write_records([
            {"normaliserat_ord": "test", "homonr": "1", "upos": "ADJ", "text": text, "stycke": "test|bar"},
        ])
        report = build_report(path)
        self.assertEqual(1, report["at_hard_cap"])
        self.assertEqual(1, report["with_bar"])
        self.assertTrue(report["records"][0]["at_hard_cap"])

    def test_reuses_rules_for_complete_hyphenated_lemmas(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "dansk-svensk",
                "upos": "ADJ",
                "text": "+t +a",
                "stycke": "dansk-svensk",
            },
            {
                "normaliserat_ord": "tv-övervakad",
                "upos": "ADJ",
                "text": "tv-övervakat +e",
                "stycke": "tv-övervakad",
            },
        ])
        report = build_report(path)
        self.assertEqual(2, report["interpreted_simple_records"])
        rows = {row["lemma"]: row for row in report["records"]}
        self.assertEqual(
            ["dansk-svensk", "dansk-svenskt", "dansk-svenska"],
            rows["dansk-svensk"]["forms"],
        )
        self.assertEqual(
            ["tv-övervakad", "tv-övervakat", "tv-övervakade"],
            rows["tv-övervakad"]["forms"],
        )
        self.assertEqual(
            "hyphenated_regular_t_a",
            rows["dansk-svensk"]["rule"],
        )

    def test_keeps_suffix_entries_non_playable(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "-aktig",
                "upos": "ADJ",
                "text": "+t +a",
                "stycke": "-aktig",
            },
        ])
        report = build_report(path)
        self.assertEqual(0, report["interpreted_simple_records"])
        self.assertEqual(1, report["intentionally_excluded_records"])
        self.assertEqual(0, report["unresolved_records"])
        self.assertEqual(
            {"suffix_or_prefix_lemma": 1},
            report["intentionally_excluded_reason_counts"],
        )
        self.assertEqual([], report["records"][0]["forms"])

    def test_excludes_multiword_lemmas_but_reports_real_parser_gaps(self) -> None:
        path = self.write_records([
            {
                "normaliserat_ord": "livs levande",
                "upos": "ADJ",
                "text": "(null)",
                "stycke": "livs levande",
            },
            {
                "normaliserat_ord": "okänd",
                "upos": "ADJ",
                "text": "helt okänd notation",
                "stycke": "okänd",
            },
        ])
        report = build_report(path)
        self.assertEqual(1, report["intentionally_excluded_records"])
        self.assertEqual(1, report["unresolved_records"])
        self.assertEqual(
            {"multiword_lemma": 1},
            report["intentionally_excluded_reason_counts"],
        )
        self.assertEqual(
            {"unparsed_singleword_pattern": 1},
            report["unresolved_reason_counts"],
        )


if __name__ == "__main__":
    unittest.main()
