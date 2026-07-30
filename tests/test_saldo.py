from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.msd import Msd
from swedish_wordlist_tools.saldo import read_saldo_analyses, read_saldo_legacy


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns="urn:test">
  <Lexicon>
    <LexicalEntry id="hypotalamus..nn.1">
      <Lemma>
        <FormRepresentation>
          <feat att="writtenForm" val="hypotalamus"/>
        </FormRepresentation>
      </Lemma>
      <WordForm>
        <feat att="writtenForm" val="hypotalamus"/>
        <feat att="msd" val="ci"/>
      </WordForm>
      <WordForm>
        <feat att="writtenForm" val="hypotalamusen"/>
        <feat att="msd" val="sg def nom"/>
      </WordForm>
      <WordForm>
        <feat att="writtenForm" val="hypotalamusens"/>
        <feat att="msd" val="sg def gen"/>
      </WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""


class SaldoTests(unittest.TestCase):
    def test_preserves_saldo_word_forms_and_parses_msd_losslessly(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "saldo.xml"
            path.write_text(SALDO_XML, encoding="utf-8")
            analysis = read_saldo_analyses(path)["hypotalamus"][0]

        self.assertEqual(analysis.entry_id, "hypotalamus..nn.1")
        self.assertEqual(analysis.upos, "NOUN")
        self.assertEqual(analysis.lemmas, frozenset({"hypotalamus"}))
        self.assertTrue(all(isinstance(form.msd, Msd) for form in analysis.word_forms))
        self.assertEqual(
            [(form.written_form, str(form.msd)) for form in analysis.word_forms],
            [
                ("hypotalamus", "ci"),
                ("hypotalamusen", "sg def nom"),
                ("hypotalamusens", "sg def gen"),
            ],
        )
        self.assertEqual(analysis.forms_for_msd("sg def gen"), ("hypotalamusens",))
        self.assertEqual(
            analysis.forms_for_msd(Msd.parse("sg def gen")),
            ("hypotalamusens",),
        )

    def test_legacy_view_keeps_word_forms_with_raw_msd(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "saldo.xml"
            path.write_text(SALDO_XML, encoding="utf-8")
            analysis = read_saldo_legacy(path)["hypotalamus"][0]

        self.assertEqual(
            analysis["forms"],
            {"hypotalamus", "hypotalamusen", "hypotalamusens"},
        )
        self.assertEqual(
            analysis["word_forms"][0],
            {
                "writtenForm": "hypotalamus",
                "msd": "ci",
                "features": {"writtenForm": "hypotalamus", "msd": "ci"},
            },
        )


if __name__ == "__main__":
    unittest.main()
