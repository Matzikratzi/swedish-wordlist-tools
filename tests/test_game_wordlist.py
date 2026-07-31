from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.game_wordlist import build_game_wordlist, filter_game_words, normalise_game_word


class GameWordlistTests(unittest.TestCase):
    def test_accepts_only_contiguous_letter_words(self) -> None:
        self.assertEqual(normalise_game_word("Abakus"), "abakus")
        self.assertEqual(normalise_game_word("räksmörgås"), "räksmörgås")
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

    def test_builds_game_file_and_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saldo.txt"
            output = root / "game.txt"
            report_path = root / "report.json"
            source.write_text("A\na\nA-kassa\nabakus\nAbakus\nälg\n", encoding="utf-8")
            report = build_game_wordlist(source, output, report_path)
            self.assertEqual(output.read_text(encoding="utf-8"), "abakus\nälg\n")
            self.assertTrue(report_path.exists())
            self.assertEqual(report["game_words"], 2)


if __name__ == "__main__":
    unittest.main()
