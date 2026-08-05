from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from swedish_wordlist_tools.game_wordlist import (
    build_game_wordlist,
    canonical_adjective_forms,
    filter_game_words,
    normalise_game_word,
    standalone_saldo_forms,
)


SALDO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns="urn:test">
  <Lexicon>
    <LexicalEntry id="abborrpinne..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="abborrpinne"/></FormRepresentation></Lemma>
      <WordForm><feat att="writtenForm" val="abborrpinne"/><feat att="msd" val="sg indef nom"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinnes"/><feat att="msd" val="sg indef gen"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinnen"/><feat att="msd" val="sg def nom"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinnens"/><feat att="msd" val="sg def gen"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinn"/><feat att="msd" val="ci"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinn"/><feat att="msd" val="cm"/></WordForm>
      <WordForm><feat att="writtenForm" val="abborrpinn-"/><feat att="msd" val="sms"/></WordForm>
    </LexicalEntry>
    <LexicalEntry id="abbe..nn.1">
      <Lemma><FormRepresentation><feat att="writtenForm" val="abbé"/></FormRepresentation></Lemma>
      <WordForm><feat att="writtenForm" val="abbén"/><feat att="msd" val="sg def nom"/></WordForm>
    </LexicalEntry>
  </Lexicon>
</LexicalResource>
"""


class GameWordlistTests(unittest.TestCase):
    def test_accepts_unicode_letter_words(self) -> None:
        self.assertEqual(normalise_game_word("Abakus"), "abakus")
        self.assertEqual(normalise_game_word("räksmörgås"), "räksmörgås")
        self.assertEqual(normalise_game_word("ABBÉ"), "abbé")
        self.assertIsNone(normalise_game_word("a"))
        self.assertIsNone(normalise_game_word("A-aktie"))
        self.assertIsNone(normalise_game_word("a cappella"))
        self.assertIsNone(normalise_game_word("no man's land"))
        self.assertIsNone(normalise_game_word("A-"))
        self.assertIsNone(normalise_game_word("3D"))

    def test_casefolds_and_deduplicates(self) -> None:
        words, report = filter_game_words([
            "Abakus", "abakus", "A-kassa", "a cappella", "a", "Älg",
        ])
        self.assertEqual(words, ["abakus", "älg"])
        self.assertEqual(report["source_forms"], 6)
        self.assertEqual(report["rejected_non_playable_forms"], 3)
        self.assertEqual(report["duplicate_after_normalisation"], 1)
        self.assertEqual(report["game_words"], 2)

    def test_excludes_compound_stems_but_keeps_inflections_and_accents(self) -> None:
        with TemporaryDirectory() as directory:
            saldo_path = Path(directory) / "saldo.xml"
            saldo_path.write_text(SALDO_XML, encoding="utf-8")
            allowed = standalone_saldo_forms(saldo_path)

        self.assertIn("abborrpinne", allowed)
        self.assertIn("abborrpinnes", allowed)
        self.assertIn("abborrpinnens", allowed)
        self.assertIn("abbé", allowed)
        self.assertIn("abbén", allowed)
        self.assertNotIn("abborrpinn", allowed)
        self.assertNotIn("abborrpinn-", allowed)

    def test_reads_canonical_adjective_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "adjectives.jsonl"
            path.write_text(
                json.dumps({
                    "lemma": "allgod",
                    "forms": [
                        {"written_form": "allgod"},
                        {"written_form": "allgott"},
                        {"written_form": "allgoda"},
                    ],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                canonical_adjective_forms(path),
                {"allgod", "allgott", "allgoda"},
            )

    def test_builds_game_file_and_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saldo.txt"
            saldo_path = root / "saldo.xml"
            adjective_path = root / "adjectives.jsonl"
            output = root / "game.txt"
            report_path = root / "report.json"
            source.write_text(
                "abborrpinn\nabborrpinne\nabborrpinnes\nabborrpinnens\nabbé\nabbén\n",
                encoding="utf-8",
            )
            saldo_path.write_text(SALDO_XML, encoding="utf-8")
            adjective_path.write_text(
                json.dumps({
                    "lemma": "allgod",
                    "forms": [
                        {"written_form": "allgod"},
                        {"written_form": "allgott"},
                    ],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report = build_game_wordlist(
                source,
                saldo_path,
                adjective_path,
                output,
                report_path,
            )
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "abborrpinne\nabborrpinnens\nabborrpinnes\nabbé\nabbén\nallgod\nallgott\n",
            )
            self.assertTrue(report_path.exists())
            self.assertEqual(report["rejected_non_standalone_saldo_forms"], 1)
            self.assertEqual(report["canonical_adjective_form_count"], 2)
            self.assertEqual(report["game_words"], 7)

    def test_keeps_adjective_form_missing_from_saldo(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saldo.txt"
            saldo_path = root / "saldo.xml"
            adjective_path = root / "adjectives.jsonl"
            output = root / "game.txt"
            report_path = root / "report.json"
            source.write_text("abborrpinne\n", encoding="utf-8")
            saldo_path.write_text(SALDO_XML, encoding="utf-8")
            adjective_path.write_text(
                json.dumps({
                    "lemma": "durabel",
                    "forms": [{"written_form": "durabla"}],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            build_game_wordlist(
                source,
                saldo_path,
                adjective_path,
                output,
                report_path,
            )

            self.assertIn("durabla", output.read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
