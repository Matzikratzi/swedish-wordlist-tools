from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_remaining_verbs import build_report, render_text


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

    def record(
        self,
        lemma: str,
        text: object,
        stycke: str = "",
        *,
        homonr: str = "",
        ordkl: str = "v.",
    ) -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "homonr": homonr,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": ordkl,
        }

    def test_reports_only_uninterpreted_rows(self) -> None:
        path = self.write_records([
            self.record("abonnera", "+de +t", "abonnera"),
            self.record("förbaske", None, "förbaske", homonr="1"),
        ])

        report = build_report(path)

        self.assertEqual(2, report["verb_records"])
        self.assertEqual(1, report["interpreted_records"])
        self.assertEqual(1, report["remaining_records"])
        self.assertEqual("förbaske", report["records"][0]["lemma"])
        self.assertEqual("1", report["records"][0]["homonr"])
        self.assertEqual("", report["records"][0]["compound_notation"])
        self.assertEqual({"missing_pattern": 1}, report["reason_counts"])
        text = render_text(report)
        self.assertIn("förbaske (homonr=1)", text)
        self.assertNotIn("stycke=", text)

    def test_marks_hard_cap_and_exact_compound_head(self) -> None:
        # Keep this fixture deliberately outside all supported verb syntaxes.
        # Alphabetic padding would accidentally look like a valid two-form row.
        capped = "unknown syntax!".ljust(50, "!")
        self.assertEqual(50, len(capped))
        path = self.write_records([
            self.record("skriva", "skrev, skrivit, pres. skriver", "skriva"),
            self.record("avskriva", capped, "av|skriva", homonr="2"),
        ])

        report = build_report(path)
        row = report["records"][0]

        self.assertTrue(row["at_hard_cap"])
        self.assertTrue(row["bar_marked"])
        self.assertEqual("av|skriva", row["compound_notation"])
        self.assertEqual("skriva", row["head_key"])
        self.assertTrue(row["exact_head_found"])
        self.assertEqual(1, report["hard_cap_counts"]["at_hard_cap"])
        self.assertEqual(1, report["compound_head_counts"]["exact_head_found"])
        text = render_text(report)
        self.assertIn("avskriva (homonr=2)", text)
        self.assertIn("compound='av|skriva'", text)


if __name__ == "__main__":
    unittest.main()
