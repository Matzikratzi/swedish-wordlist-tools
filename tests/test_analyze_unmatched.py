from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from swedish_wordlist_tools.analyze_unmatched import analyse_unmatched


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Lexicon>
  <LexicalEntry id="a-aktie..nn.1">
    <Lemma><FormRepresentation>
      <feat att="writtenForm" val="A-aktie"/>
      <feat att="partOfSpeech" val="nn"/>
    </FormRepresentation></Lemma>
    <WordForm><feat att="writtenForm" val="A-aktien"/><feat att="msd" val="sg def nom"/></WordForm>
  </LexicalEntry>
  <LexicalEntry id="ide..nn.1">
    <Lemma><FormRepresentation>
      <feat att="writtenForm" val="idé"/>
      <feat att="partOfSpeech" val="nn"/>
    </FormRepresentation></Lemma>
    <WordForm><feat att="writtenForm" val="idén"/><feat att="msd" val="sg def nom"/></WordForm>
  </LexicalEntry>
  <LexicalEntry id="cykelhjalm..nn.1">
    <Lemma><FormRepresentation>
      <feat att="writtenForm" val="cykelhjälm"/>
      <feat att="partOfSpeech" val="nn"/>
    </FormRepresentation></Lemma>
    <WordForm><feat att="writtenForm" val="cykelhjälmen"/><feat att="msd" val="sg def nom"/></WordForm>
  </LexicalEntry>
</Lexicon>
"""


class AnalyzeUnmatchedTests(unittest.TestCase):
    def test_writes_grouped_jsonl_csv_and_summary(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saol-only.jsonl"
            saldo = root / "saldo.xml"
            details = root / "details.jsonl"
            csv_path = root / "details.csv"
            summary_path = root / "summary.json"
            source.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {"lemma": "Aaktie", "upos": "NOUN", "ordkl": "subst."},
                        {"lemma": "ide", "upos": "NOUN", "ordkl": "subst."},
                        {"lemma": "cykelhjälmen", "upos": "NOUN", "ordkl": "subst."},
                        {"lemma": "cykelhjäl", "upos": "NOUN", "ordkl": "subst."},
                        {"lemma": "heltokänd", "upos": "ADJ", "ordkl": "adj."},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            saldo.write_text(SALDO_XML, encoding="utf-8")

            summary = analyse_unmatched(source, saldo, details, csv_path, summary_path)

            rows = [json.loads(line) for line in details.read_text(encoding="utf-8").splitlines()]
            by_lemma = {row["lemma"]: row for row in rows}
            self.assertEqual(by_lemma["Aaktie"]["analysis_reason"], "separator_difference_same_upos")
            self.assertEqual(by_lemma["ide"]["analysis_reason"], "diacritic_difference_same_upos")
            self.assertEqual(by_lemma["cykelhjälmen"]["analysis_reason"], "wordform_same_upos")
            self.assertEqual(by_lemma["cykelhjäl"]["analysis_reason"], "single_edit_same_upos")
            self.assertEqual(by_lemma["heltokänd"]["analysis_reason"], "no_candidate")
            self.assertEqual(summary["records"], 5)
            self.assertTrue(csv_path.exists())
            self.assertTrue(summary_path.exists())


if __name__ == "__main__":
    unittest.main()
