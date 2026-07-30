from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from swedish_wordlist_tools.compare_sources import compare_sources, read_saldo


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns="urn:test">
  <Lexicon>
    <LexicalEntry id="abakus..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="abakus"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="abakusen"/></FormRepresentation></WordForm>
      <WordForm><FormRepresentation><feat att="writtenForm" val="abakuser"/></FormRepresentation></WordForm>
    </LexicalEntry>
    <LexicalEntry id="saldo-only..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="saldoord"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="saldoordet"/></FormRepresentation></WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""

SAOL_JSONL = """{"id":"1","normaliserat_ord":"abakus","text":"+en +er","upos":"NOUN"}
{"id":"2","normaliserat_ord":"saolord","text":"+et; pl. +","upos":"NOUN"}
"""


class CompareSourcesTests(unittest.TestCase):
    def test_reads_namespaced_saldo_written_forms(self) -> None:
        with TemporaryDirectory() as directory:
            saldo_path = Path(directory) / "saldo.xml"
            saldo_path.write_text(SALDO_XML, encoding="utf-8")
            saldo = read_saldo(saldo_path)
        self.assertEqual(saldo["abakus"]["forms"], {"abakus", "abakusen", "abakuser"})

    def test_builds_target_and_two_exception_lists(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            saol_path = root / "saol.jsonl"
            saldo_path = root / "saldo.xml"
            target = root / "target.txt"
            saol_only = root / "saol-only.jsonl"
            saldo_only = root / "saldo-only.jsonl"
            report_path = root / "report.json"
            saol_path.write_text(SAOL_JSONL, encoding="utf-8")
            saldo_path.write_text(SALDO_XML, encoding="utf-8")

            report = compare_sources(
                saol_path, saldo_path, target, saol_only, saldo_only, report_path
            )

            target_forms = target.read_text(encoding="utf-8").splitlines()
            saol_rows = [json.loads(line) for line in saol_only.read_text(encoding="utf-8").splitlines()]
            saldo_rows = [json.loads(line) for line in saldo_only.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(target_forms, ["abakus", "abakusen", "abakuser"])
        self.assertEqual(saol_rows[0]["lemma"], "saolord")
        self.assertEqual(saol_rows[0]["generated_forms"], ["saolord", "saolordet"])
        self.assertEqual(saldo_rows[0]["lemmas"], ["saldoord"])
        self.assertNotIn("saldoord", target_forms)
        self.assertEqual(report["saol_matched_records"], 1)
        self.assertEqual(report["saol_only_records"], 1)
        self.assertEqual(report["saldo_only_lemmas"], 1)
        self.assertEqual(report["target_unique_forms"], 3)


if __name__ == "__main__":
    unittest.main()
