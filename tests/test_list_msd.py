from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.list_msd import format_summary, format_text, inventory_msd


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns="urn:test">
  <Lexicon>
    <LexicalEntry id="bil..nn.1">
      <Lemma><feat att="writtenForm" val="bil"/></Lemma>
      <WordForm><feat att="writtenForm" val="bil"/><feat att="msd" val="ci"/></WordForm>
      <WordForm><feat att="writtenForm" val="bilen"/><feat att="msd" val="sg def nom"/></WordForm>
    </LexicalEntry>
    <LexicalEntry id="fila..vb.1">
      <Lemma><feat att="writtenForm" val="fila"/></Lemma>
      <WordForm><feat att="writtenForm" val="fila"/><feat att="msd" val="ci"/></WordForm>
      <WordForm><feat att="writtenForm" val="filar"/><feat att="msd" val="pres ind aktiv"/></WordForm>
      <WordForm><feat att="writtenForm" val="filas"/></WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""


class ListMsdTests(unittest.TestCase):
    def test_counts_raw_msd_globally_and_by_upos(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "saldo.xml"
            path.write_text(SALDO_XML, encoding="utf-8")
            report = inventory_msd(path)

        self.assertEqual(report["lexical_entries"], 2)
        self.assertEqual(report["word_forms"], 5)
        self.assertEqual(report["unique_msd"], 4)
        self.assertEqual(report["msd"][0], {"msd": "ci", "count": 2})
        self.assertIn({"msd": "sg def nom", "count": 1}, report["by_upos"]["NOUN"])
        self.assertIn({"msd": "pres ind aktiv", "count": 1}, report["by_upos"]["VERB"])
        self.assertIn({"msd": "(saknas)", "count": 1}, report["by_upos"]["VERB"])

    def test_formats_readable_report(self) -> None:
        report = {
            "lexical_entries": 1,
            "word_forms": 1,
            "unique_msd": 1,
            "msd": [{"msd": "ci", "count": 1}],
            "by_upos": {"NOUN": [{"msd": "ci", "count": 1}]},
        }
        text = format_text(report)
        self.assertIn("Unika msd-koder: 1", text)
        self.assertIn("        1  ci", text)
        self.assertIn("NOUN:", text)

    def test_formats_concise_summary_for_output_file(self) -> None:
        report = {
            "lexical_entries": 2,
            "word_forms": 5,
            "unique_msd": 4,
        }
        text = format_summary(report, Path("report.json"))
        self.assertEqual(
            text,
            "LexicalEntry: 2, WordForm: 5, unika msd-koder: 4. Skrev report.json\n",
        )
        self.assertNotIn("Alla msd-koder", text)


if __name__ == "__main__":
    unittest.main()
