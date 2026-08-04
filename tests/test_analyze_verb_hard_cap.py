from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_hard_cap import build_report


class AnalyzeVerbHardCapTests(unittest.TestCase):
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

    def test_reports_only_rows_at_hard_cap(self) -> None:
        capped = "pres. och: pret.; sup. måst; prov. och: finl. inf."
        self.assertEqual(50, len(capped))
        path = self.write_records([
            {
                "normaliserat_ord": "måste",
                "homonr": "1",
                "text": capped,
                "upos": "VERB",
                "ordkl": "v.",
            },
            {
                "normaliserat_ord": "abonnera",
                "homonr": "1",
                "text": "+de +t",
                "upos": "VERB",
                "ordkl": "v.",
            },
        ])

        report = build_report(path)

        self.assertEqual(1, report["records_at_hard_cap"])
        row = report["records"][0]
        self.assertEqual("måste", row["lemma"])
        self.assertEqual("inf", row["last_label"])
        self.assertEqual(["måste", "måst"], row["playable_forms"])
        self.assertTrue(row["possible_missing_after_cap"])

    def test_delimiter_end_is_not_flagged_as_open_tail(self) -> None:
        capped = "skrev, skrivit".ljust(49, "x") + ","
        self.assertEqual(50, len(capped))
        path = self.write_records([
            {
                "normaliserat_ord": "skriva",
                "homonr": "1",
                "text": capped,
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])

        report = build_report(path)
        row = report["records"][0]
        self.assertFalse(row["possible_missing_after_cap"])


if __name__ == "__main__":
    unittest.main()
