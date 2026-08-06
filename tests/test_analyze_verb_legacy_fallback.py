from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_legacy_fallback import build_report


class AnalyzeVerbLegacyFallbackTests(unittest.TestCase):
    def write_records(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_lists_only_legacy_fallback_records(self) -> None:
        path = self.write_records(
            [
                {"normaliserat_ord": "abonnera", "upos": "VERB", "text": "+de +t"},
                {"normaliserat_ord": "lyss", "upos": "VERB", "text": "pres. lyss; imper. lys"},
                {"normaliserat_ord": "torde", "upos": "VERB", "text": "pres. ibl. tör"},
                {"normaliserat_ord": "gå an", "upos": "VERB", "text": "gick an, gått an"},
            ]
        )
        report = build_report(path)
        self.assertEqual(1, report["legacy_fallback_records"])
        self.assertEqual({"explicit_attested_forms": 1}, report["fallback_kind_counts"])
        self.assertEqual("lyss", report["records"][0]["lemma"])
        self.assertEqual(["lyss", "lys"], report["records"][0]["forms"])


if __name__ == "__main__":
    unittest.main()
