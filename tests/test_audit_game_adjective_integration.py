from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.audit_game_adjective_integration import (
    build_audit,
    confirmed_gap_forms,
)


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns="urn:test">
  <Lexicon>
    <LexicalEntry id="abborrpinne..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="abborrpinne"/></FormRepresentation></Lemma>
      <WordForm><feat att="writtenForm" val="abborrpinne"/><feat att="msd" val="sg indef nom"/></WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""


class AuditGameAdjectiveIntegrationTests(unittest.TestCase):
    def test_reads_only_confirmed_gap_forms(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "adjudication.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({
                        "written_form": "durabla",
                        "final_adjudication": "confirmed_saldo_form_gap",
                    }),
                    json.dumps({
                        "written_form": "frånskilda",
                        "final_adjudication": "confirmed_saldo_adjective_analysis_gap",
                    }),
                    json.dumps({
                        "written_form": "facetterad",
                        "final_adjudication": "saldo_adjective_alignment",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                confirmed_gap_forms(path),
                {"durabla", "frånskilda"},
            )

    def test_audit_confirms_clean_additive_integration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            saldo = root / "saldo.xml"
            adjectives = root / "adjectives.jsonl"
            adjudication = root / "adjudication.jsonl"

            source.write_text("abborrpinne\n", encoding="utf-8")
            saldo.write_text(SALDO_XML, encoding="utf-8")
            adjectives.write_text(
                json.dumps({
                    "lemma": "durabel",
                    "forms": [
                        {"written_form": "durabel"},
                        {"written_form": "durabla"},
                    ],
                }) + "\n",
                encoding="utf-8",
            )
            adjudication.write_text(
                json.dumps({
                    "written_form": "durabla",
                    "final_adjudication": "confirmed_saldo_form_gap",
                }) + "\n",
                encoding="utf-8",
            )

            report, added = build_audit(source, saldo, adjectives, adjudication)

            self.assertTrue(report["integration_is_clean"])
            self.assertEqual(1, report["baseline_game_words"])
            self.assertEqual(3, report["integrated_game_words"])
            self.assertEqual(2, report["added_game_words"])
            self.assertEqual(0, report["removed_game_words"])
            self.assertEqual(0, report["unexpected_added_words"])
            self.assertEqual(1, report["confirmed_gap_forms_present"])
            self.assertEqual(0, report["confirmed_gap_forms_missing"])
            self.assertEqual(["durabel", "durabla"], added)


if __name__ == "__main__":
    unittest.main()
