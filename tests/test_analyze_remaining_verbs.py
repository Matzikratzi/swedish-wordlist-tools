from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_remaining_verbs import build_report


class AnalyzeRemainingVerbsTests(unittest.TestCase):
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

    def record(self, lemma: str, text: object, stycke: str = "") -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_reports_only_uninterpreted_rows(self) -> None:
        path = self.write_records([
            self.record("abonnera", "+de +t", "abonnera"),
            self.record("förbaske", None, "förbaske"),
        ])

        report = build_report(path)

        self.assertEqual(2, report["verb_records"])
        self.assertEqual(1, report["interpreted_records"])
        self.assertEqual(1, report["remaining_records"])
        self.assertEqual("förbaske", report["records"][0]["lemma"])
        self.assertEqual({"missing_pattern": 1}, report["reason_counts"])

    def test_marks_hard_cap_and_exact_compound_head(self) -> None:
        capped = "unknown syntax that reaches the source hard cap xxxx"
        self.assertEqual(50, len(capped))
        path = self.write_records([
            self.record("skriva", "skrev, skrivit, pres. skriver", "skriva"),
            self.record("avskriva", capped, "av|skriva"),
        ])

        report = build_report(path)
        row = report["records"][0]

        self.assertTrue(row["at_hard_cap"])
        self.assertTrue(row["bar_marked"])
        self.assertEqual("skriva", row["head_key"])
        self.assertTrue(row["exact_head_found"])
        self.assertEqual(1, report["hard_cap_counts"]["at_hard_cap"])
        self.assertEqual(1, report["compound_head_counts"]["exact_head_found"])


if __name__ == "__main__":
    unittest.main()
