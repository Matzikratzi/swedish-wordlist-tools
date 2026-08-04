from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_verb_forms import build_verb_forms


class ExportVerbSlotsOnlyTests(unittest.TestCase):
    def write_jsonl(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".jsonl", delete=False
        )
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return Path(handle.name)

    def test_unmarked_raw_text_token_cannot_bypass_slot_interpreter(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "testa",
                "text": "unknown syntax anfa",
                "stycke": "testa",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])
        self.addCleanup(path.unlink)

        words, report = build_verb_forms(path)

        self.assertNotIn("anfa", words)
        self.assertEqual([], words)
        self.assertEqual(0, report["interpreted_records"])

    def test_hard_cap_fragment_is_not_exported_from_a_valid_row(self) -> None:
        text = "sjöng, sjungit, sjungen sjunget sjungna, pres. sju"
        self.assertEqual(50, len(text))
        path = self.write_jsonl([
            {
                "normaliserat_ord": "sjunga",
                "text": text,
                "stycke": "sjunga",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])
        self.addCleanup(path.unlink)

        words, report = build_verb_forms(path)

        self.assertIn("sjunga", words)
        self.assertIn("sjöng", words)
        self.assertIn("sjungit", words)
        self.assertNotIn("sju", words)
        self.assertEqual(1, report["interpreted_records"])


if __name__ == "__main__":
    unittest.main()
