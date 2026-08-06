from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verbs import build_report


class AnalyzeVerbsTests(unittest.TestCase):
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

    def test_separates_interpreted_excluded_and_uninterpreted(self) -> None:
        path = self.write_records(
            [
                {
                    "normaliserat_ord": "hålla",
                    "upos": "VERB",
                    "text": "höll, hållit",
                    "stycke": "håll·a",
                },
                {
                    "normaliserat_ord": "-hålla",
                    "upos": "VERB",
                    "text": "-höll, -hållit",
                    "stycke": "-håll·a",
                },
                {
                    "normaliserat_ord": "gå an",
                    "upos": "VERB",
                    "text": "gick an, gått an",
                    "stycke": "gå an",
                },
                {
                    "normaliserat_ord": "mystifiera",
                    "upos": "VERB",
                    "text": "helt okänd syntax med prosa",
                    "stycke": "mystifiera",
                },
                {
                    "normaliserat_ord": "sak",
                    "upos": "NOUN",
                    "text": "+en; pl. +er",
                    "stycke": "sak",
                },
            ]
        )
        report = build_report(path)
        self.assertEqual(4, report["verb_records"])
        self.assertEqual(1, report["interpreted_playable_records"])
        self.assertEqual(2, report["intentionally_excluded_records"])
        self.assertEqual(1, report["genuinely_uninterpreted_records"])
        self.assertEqual(
            {"suffix_or_prefix_lemma": 1, "multiword_lemma": 1},
            report["exclusion_counts"],
        )

    def test_counts_no_inflection_as_interpreted(self) -> None:
        path = self.write_records(
            [
                {
                    "normaliserat_ord": "testverb",
                    "upos": "VERB",
                    "text": "ingen böjning",
                    "stycke": "testverb",
                }
            ]
        )
        report = build_report(path)
        self.assertEqual(1, report["interpreted_playable_records"])
        self.assertEqual(0, report["genuinely_uninterpreted_records"])


if __name__ == "__main__":
    unittest.main()
