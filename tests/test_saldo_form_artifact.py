from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.saldo_form_artifact import read_saldo_forms


class SaldoFormArtifactTests(unittest.TestCase):
    def test_reads_materialized_forms_by_lemma(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saldo-forms.jsonl"
            row = {
                "id": "bankväsen..nn.1",
                "upos": "NOUN",
                "lemmas": ["bankväsen"],
                "forms": [
                    "bankväsen",
                    "bankväsens",
                    "bankväsendet",
                    "bankväsendets",
                ],
            }
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            saldo = read_saldo_forms(path)
            self.assertEqual(1, len(saldo["bankväsen"]))
            analysis = saldo["bankväsen"][0]
            self.assertEqual("NOUN", analysis["upos"])
            self.assertEqual(set(row["forms"]), analysis["forms"])


if __name__ == "__main__":
    unittest.main()
