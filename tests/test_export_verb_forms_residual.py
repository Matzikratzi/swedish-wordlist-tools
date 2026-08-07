from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_verb_forms import build_verb_forms


class ExportVerbFormsResidualTests(unittest.TestCase):
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

    def test_exports_residual_forms_and_excludes_nonplayable_lemmas(self) -> None:
        records = [
            {"normaliserat_ord": "förbaske", "upos": "VERB", "text": None},
            {"normaliserat_ord": "lär", "upos": "VERB", "text": None},
            {"normaliserat_ord": "månde", "upos": "VERB", "text": None},
            {"normaliserat_ord": "nåde", "upos": "VERB", "text": None},
            {"normaliserat_ord": "lyster", "upos": "VERB", "text": "pres."},
            {
                "normaliserat_ord": "måste",
                "upos": "VERB",
                "text": "pres. och: pret.; sup. måst; prov. och: finl. inf.",
            },
            {"normaliserat_ord": "torde", "upos": "VERB", "text": "pres. ibl. tör"},
            {"normaliserat_ord": "må", "upos": "VERB", "text": "måtte"},
            {"normaliserat_ord": "gå an", "upos": "VERB", "text": "gick, gått"},
            {"normaliserat_ord": "-göra", "upos": "VERB", "text": "+de +t"},
        ]
        path = self.write_records(records)

        words, report = build_verb_forms(path)

        self.assertEqual(8, report["interpreted_records"])
        self.assertEqual(
            {
                "förbaske",
                "lär",
                "månde",
                "nåde",
                "lyster",
                "måste",
                "måst",
                "torde",
                "tör",
                "må",
                "måtte",
            },
            set(words),
        )
        self.assertNotIn("gå an", words)
        self.assertNotIn("gick", words)
        self.assertNotIn("gått", words)
        self.assertNotIn("göra", words)


if __name__ == "__main__":
    unittest.main()
