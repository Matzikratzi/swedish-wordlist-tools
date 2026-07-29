from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.audit import (
    audit_flags,
    build_audit,
    make_audit_row,
    sample_rows,
)
from swedish_wordlist_tools.inflect import GeneratedEntry


class AuditTests(unittest.TestCase):
    def test_flags_special_lemmas_and_upos_x(self) -> None:
        entry = GeneratedEntry(
            lemma="A-avdrag",
            pattern="+et; pl. +",
            forms=("A-avdrag", "A-avdraget"),
        )
        flags = audit_flags({"upos": "X"}, entry)
        self.assertEqual(flags, ("upos-X", "versal", "bindestreck"))

    def test_makes_row_from_real_fields(self) -> None:
        row = make_audit_row(
            {
                "id": "abc",
                "normaliserat_ord": "abakus",
                "text": "+en +er",
                "upos": "NOUN",
                "ordkl": "s.",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.record_id, "abc")
        self.assertEqual(row.forms, ("abakus", "abakusen", "abakuser"))

    def test_sampling_is_deterministic_and_limited(self) -> None:
        records = [
            {
                "id": str(index),
                "normaliserat_ord": f"ord{index}",
                "text": "+en +er",
                "upos": "NOUN",
                "ordkl": "s.",
            }
            for index in range(20)
        ]
        first, counts, _ = sample_rows(records, examples_per_pattern=5, seed=14)
        second, _, _ = sample_rows(records, examples_per_pattern=5, seed=14)
        self.assertEqual(first, second)
        self.assertEqual(counts["+en +er"], 20)
        self.assertEqual(len(first["+en +er"]), 5)

    def test_rejects_zero_examples(self) -> None:
        with self.assertRaises(ValueError):
            sample_rows([], examples_per_pattern=0, seed=14)

    def test_builds_html_with_review_controls(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.html"
            report = build_audit(fixture, output, examples_per_pattern=2, seed=14)
            document = output.read_text(encoding="utf-8")

        self.assertEqual(report["supported_records"], 2)
        self.assertEqual(report["sampled_records"], 2)
        self.assertIn("abakusen", document)
        self.assertIn("Exportera bedömningar som JSON", document)
        self.assertIn('value="wrong"', document)


if __name__ == "__main__":
    unittest.main()
