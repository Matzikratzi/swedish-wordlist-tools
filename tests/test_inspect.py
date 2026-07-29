from pathlib import Path
import unittest

from swedish_wordlist_tools.inspect import inspect_file, normalise_text


class InspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"

    def test_inspects_real_saol14_fields(self) -> None:
        report = inspect_file(self.fixture)
        self.assertEqual(report["source_records"], 4)
        self.assertEqual(report["records"], 4)
        self.assertEqual(report["fields"]["ordkl"]["present"], 4)
        self.assertEqual(report["fields"]["upos"]["present"], 4)
        self.assertEqual(report["unique_counts"]["ordkl"], 4)
        self.assertEqual(report["unique_counts"]["upos"], 2)
        self.assertEqual(report["unique_counts"]["text"], 3)
        self.assertEqual(report["missing_values"]["text"], 1)

    def test_null_marker_is_treated_as_missing(self) -> None:
        self.assertIsNone(normalise_text("(null)"))
        self.assertIsNone(normalise_text(""))
        self.assertIsNone(normalise_text(None))
        self.assertEqual(normalise_text("+en +er"), "+en +er")

    def test_text_values_include_examples(self) -> None:
        report = inspect_file(self.fixture, examples_per_value=2)
        patterns = {item["value"]: item for item in report["top_values"]["text"]}
        self.assertEqual(patterns["+en +er"]["examples"], ["abakus"])

    def test_filters_by_text(self) -> None:
        report = inspect_file(self.fixture, text_filter="+en +er")
        self.assertEqual(report["source_records"], 4)
        self.assertEqual(report["records"], 1)
        self.assertEqual(report["unique_counts"]["text"], 1)
        item = report["top_values"]["text"][0]
        self.assertEqual(item["value"], "+en +er")
        self.assertEqual(item["examples"], ["abakus"])

    def test_filters_by_upos(self) -> None:
        report = inspect_file(self.fixture, upos_filter="X")
        self.assertEqual(report["records"], 1)
        self.assertEqual(report["missing_values"]["text"], 1)
        self.assertEqual(report["unique_counts"]["upos"], 1)


if __name__ == "__main__":
    unittest.main()
