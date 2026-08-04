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


if __name__ == "__main__":
    unittest.main()
