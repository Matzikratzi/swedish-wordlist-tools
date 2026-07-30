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
    <LexicalEntry id="fil..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="fil"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="filen"/></FormRepresentation></WordForm>
    </LexicalEntry>
    <LexicalEntry id="fil..vb.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="fil"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="filar"/></FormRepresentation></WordForm>
      <WordForm><FormRepresentation><feat att="writtenForm" val="filade"/></FormRepresentation></WordForm>
    </LexicalEntry>
    <LexicalEntry id="ack..in.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="ack"/></FormRepresentation></Lemma>
    </LexicalEntry>
    <LexicalEntry id="afrika..pm.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="Afrika"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="Afrikas"/></FormRepresentation></WordForm>
    </LexicalEntry>
    <LexicalEntry id="oklar..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="oklar"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="oklaren"/></FormRepresentation></WordForm>
    </LexicalEntry>
    <LexicalEntry id="saldo-only..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="saldoord"/></FormRepresentation></Lemma>
      <WordForm><FormRepresentation><feat att="writtenForm" val="saldoordet"/></FormRepresentation></WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""

SAOL_JSONL = """{"id":"1","normaliserat_ord":"abakus","text":"+en +er","upos":"NOUN","ordkl":"subst."}
{"id":"2","normaliserat_ord":"fil","text":"+ar +ade","upos":"NOUN","ordkl":"verb","homonr":"2"}
{"id":"3","normaliserat_ord":"ack","text":"(null)","upos":"X","ordkl":"interj."}
{"id":"4","normaliserat_ord":"Afrika","text":"(null)","upos":"X","ordkl":"namn"}
{"id":"5","normaliserat_ord":"oklar","text":"","upos":"ADJ","ordkl":"adj."}
{"id":"6","normaliserat_ord":"saolord","text":"+et; pl. +","upos":"NOUN","ordkl":"s."}
{"id":"7","normaliserat_ord":"-aktig","text":"+t +a","upos":"ADJ","ordkl":"adjektiviskt slutled"}
"""


class CompareSourcesTests(unittest.TestCase):
    def test_reads_namespaced_saldo_analyses_and_word_classes(self) -> None:
        with TemporaryDirectory() as directory:
            saldo_path = Path(directory) / "saldo.xml"
            saldo_path.write_text(SALDO_XML, encoding="utf-8")
            saldo = read_saldo(saldo_path)

        self.assertEqual(len(saldo["fil"]), 2)
        by_pos = {analysis["upos"]: analysis for analysis in saldo["fil"]}
        self.assertEqual(by_pos["NOUN"]["forms"], {"fil", "filen"})
        self.assertEqual(by_pos["VERB"]["forms"], {"fil", "filar", "filade"})

    def test_builds_target_normalizes_word_classes_and_filters_affixes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            saol_path = root / "saol.jsonl"
            saldo_path = root / "saldo.xml"
            target = root / "target.txt"
            saol_only = root / "saol-only.jsonl"
            ambiguous = root / "ambiguous.jsonl"
            saldo_only = root / "saldo-only.jsonl"
            report_path = root / "report.json"
            saol_path.write_text(SAOL_JSONL, encoding="utf-8")
            saldo_path.write_text(SALDO_XML, encoding="utf-8")

            report = compare_sources(
                saol_path,
                saldo_path,
                target,
                saol_only,
                ambiguous,
                saldo_only,
                report_path,
            )

            target_forms = target.read_text(encoding="utf-8").splitlines()
            saol_rows = [json.loads(line) for line in saol_only.read_text(encoding="utf-8").splitlines()]
            ambiguous_rows = [
                json.loads(line) for line in ambiguous.read_text(encoding="utf-8").splitlines()
            ]
            saldo_rows = [json.loads(line) for line in saldo_only.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(
            target_forms,
            ["abakus", "abakusen", "abakuser", "ack", "Afrika", "Afrikas", "fil", "filade", "filar"],
        )
        self.assertNotIn("filen", target_forms)
        self.assertNotIn("-aktig", target_forms)
        self.assertEqual(saol_rows[0]["lemma"], "saolord")
        self.assertEqual(saol_rows[0]["reason"], "no_saldo_lemma")
        self.assertEqual(saol_rows[0]["generated_forms"], ["saolord", "saolordet"])
        self.assertEqual(ambiguous_rows[0]["lemma"], "oklar")
        self.assertEqual(ambiguous_rows[0]["saldo_word_classes"], ["NOUN"])
        self.assertEqual(saldo_rows[0]["lemmas"], ["saldoord"])
        self.assertNotIn("saldoord", target_forms)
        self.assertEqual(report["saol_source_records"], 7)
        self.assertEqual(report["saol_filtered_affix_records"], 1)
        self.assertEqual(report["saol_compared_records"], 6)
        self.assertEqual(report["saol_matched_records"], 4)
        self.assertEqual(report["saol_only_records"], 1)
        self.assertEqual(report["ambiguous_records"], 1)
        self.assertEqual(report["saldo_only_lemmas"], 1)
        self.assertEqual(report["target_unique_forms"], 9)


if __name__ == "__main__":
    unittest.main()
