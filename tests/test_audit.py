from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.audit import audit_flags, build_audit, make_audit_row, sample_rows
from swedish_wordlist_tools.inflect import EXPLICIT_PATTERN_GROUP, GeneratedEntry


class AuditTests(unittest.TestCase):
    def test_flags_special_lemmas_and_upos_x(self) -> None:
        entry = GeneratedEntry("A-avdrag", "+et; pl. +", ("A-avdrag", "A-avdraget"), "+et; pl. +")
        self.assertEqual(audit_flags({"upos": "X"}, entry), ("upos-X", "versal", "bindestreck"))

    def test_flags_explicit_forms(self) -> None:
        entry = GeneratedEntry("klocka", "+n klockor", ("klocka", "klockan", "klockor"), EXPLICIT_PATTERN_GROUP)
        self.assertEqual(audit_flags({"upos": "NOUN"}, entry), ("explicit-form",))

    def test_makes_row_from_real_fields(self) -> None:
        row = make_audit_row({
            "id": "abc", "normaliserat_ord": "abakus", "text": "+en +er",
            "upos": "NOUN", "ordkl": "s.", "source": "https://example.test/page.pdf",
        })
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.record_id, "abc")
        self.assertEqual(row.forms, ("abakus", "abakusen", "abakuser"))
        self.assertEqual(row.notation, "+en +er")

    def test_sampling_is_deterministic_and_limited(self) -> None:
        records = [{"id": str(i), "normaliserat_ord": f"ord{i}", "text": "+en +er", "upos": "NOUN"} for i in range(20)]
        first, counts, _ = sample_rows(records, 5, 14)
        second, _, _ = sample_rows(records, 5, 14)
        self.assertEqual(first, second)
        self.assertEqual(counts["+en +er"], 20)
        self.assertEqual(len(first["+en +er"]), 5)

    def test_rejects_zero_examples(self) -> None:
        with self.assertRaises(ValueError):
            sample_rows([], 0, 14)

    def test_builds_html_with_working_controls_links_and_batches(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.html"
            report = build_audit(fixture, output, examples_per_pattern=2, batch_size=1, seed=14)
            document = output.read_text(encoding="utf-8")
        self.assertEqual(report["supported_records"], 3)
        self.assertEqual(report["sampled_records"], 3)
        self.assertIn("abakusen", document)
        self.assertIn("abbedissor", document)
        self.assertIn("Exportera bedömningar som JSON", document)
        self.assertIn('target="_blank"', document)
        self.assertIn("Ref ↗", document)
        self.assertIn("document.querySelectorAll('.more')", document)
        self.assertIn("JSON.stringify(reviews, null, 2) + '\\n'", document)
        self.assertNotIn("JSON.stringify(reviews, null, 2) + '\n'", document)

    def test_places_all_right_button_under_generated_forms(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "audit.html"
            build_audit(fixture, output, examples_per_pattern=2, batch_size=1, seed=14)
            document = output.read_text(encoding="utf-8")
        self.assertIn('<tr class="category-actions"><td></td><td></td><td>', document)
        self.assertIn('class="all-right"', document)
        self.assertIn("Alla rätt", document)
        self.assertIn("markerar synliga obesvarade", document)
        self.assertIn("if (right && !reviews[right.name])", document)


if __name__ == "__main__":
    unittest.main()
