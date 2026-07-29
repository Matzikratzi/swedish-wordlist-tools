from pathlib import Path
import unittest

from swedish_wordlist_tools.inspect import inspect_file


class InspectTests(unittest.TestCase):
    def test_inspects_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
        report = inspect_file(fixture)
        self.assertEqual(report["records"], 3)
        self.assertEqual(report["fields"]["text"]["present"], 3)
        self.assertEqual(report["unique_counts"]["ordklass"], 3)


if __name__ == "__main__":
    unittest.main()
