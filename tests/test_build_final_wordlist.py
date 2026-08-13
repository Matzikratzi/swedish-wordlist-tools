from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.build_final_wordlist import build_final_wordlist, build_rows


def row(form: str, source_id: str = "1") -> dict[str, object]:
    return {
        "form": form,
        "classification": "CLASSIFIED",
        "upos": ["NOUN"],
        "source_record_ids": [source_id],
        "provenance": ["test"],
    }


class BuildFinalWordlistTests(unittest.TestCase):
    def test_normalises_deduplicates_and_reports_every_rejection(self) -> None:
        rows, rejected, summary = build_rows([
            row("Abakus", "1"),
            row("abakus", "2"),
            row("ho\u0308gan", "3"),
            row("x", "4"),
            row("a-b", "5"),
            row("r2", "6"),
            row("rock'n", "7"),
            row("a/b", "8"),
        ])
        self.assertEqual(["abakus", "högan"], [item["form"] for item in rows])
        self.assertEqual(["1", "2"], rows[0]["source_record_ids"])
        self.assertEqual(1, summary["duplicates_after_nfc_casefold"])
        self.assertEqual(5, summary["rejected_rows"])
        self.assertEqual({
            "CONTAINS_APOSTROPHE": 1,
            "CONTAINS_DIGIT": 1,
            "CONTAINS_HYPHEN": 1,
            "CONTAINS_OTHER_NONLETTER": 1,
            "ONE_CHARACTER": 1,
        }, summary["rejections_by_reason"])
        self.assertEqual(5, len(rejected))
        self.assertFalse(summary["saldo_affects_output"])

    def test_writes_matching_text_jsonl_and_hash_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shared.jsonl"
            source.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in [row("Öga"), row("högan")]) + "\n",
                encoding="utf-8",
            )
            output = root / "gamewords.txt"
            jsonl = root / "gamewords.jsonl"
            rejected = root / "rejected.jsonl"
            summary = root / "summary.json"
            report = build_final_wordlist(source, output, jsonl, rejected, summary)

            self.assertEqual(["högan", "öga"], output.read_text(encoding="utf-8").splitlines())
            jsonl_forms = [json.loads(line)["form"] for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["högan", "öga"], jsonl_forms)
            self.assertEqual(64, len(report["source_sha256"]))
            self.assertEqual(64, len(report["output_sha256"]))
            self.assertEqual(report, json.loads(summary.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
