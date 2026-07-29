from pathlib import Path
import tempfile
import unittest

from swedish_wordlist_tools.jsonl import read_jsonl


class JsonlTests(unittest.TestCase):
    def test_reads_objects_and_ignores_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            path.write_text('{"ord":"apa"}\n\n{"ord":"banan"}\n', encoding="utf-8")
            self.assertEqual([row["ord"] for row in read_jsonl(path)], ["apa", "banan"])

    def test_reports_invalid_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            path.write_text('{"ord":"apa"}\nnot-json\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                list(read_jsonl(path))


if __name__ == "__main__":
    unittest.main()
