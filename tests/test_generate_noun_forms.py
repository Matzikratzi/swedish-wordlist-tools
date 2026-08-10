from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms import (
    canonical_noun_row,
    generate_noun_artifact,
    render_comparison,
)
from swedish_wordlist_tools.noun_paradigm import _complete_from_slots, _entry_from_interpreted_row, _genitive
from swedish_wordlist_tools.saol_row_interpreter import InterpretedRow, KeyForm


class GenerateNounFormsTests(unittest.TestCase):
    def test_ignores_non_nouns(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "glad",
            "upos": "ADJ",
            "text": "glatt glada",
        })
        self.assertIsNone(row)
        self.assertIsNone(comparison)

    def test_generates_regular_noun_with_provenance(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "bil",
            "upos": "NOUN",
            "text": "+en +ar",
            "homonr": "1",
            "subnr": 7,
            "stycke": "bil",
        })
        self.assertIsNotNone(row)
        assert row is not None
        written = {form["written_form"] for form in row["forms"]}
        self.assertIn("bil", written)
        self.assertIn("bilen", written)
        self.assertIn("bilar", written)
        self.assertEqual(
            {"noun_interpreter", "noun_completion"},
            {form["source_stage"] for form in row["forms"]},
        )
        self.assertNotIn("base_generator", {form["source_stage"] for form in row["forms"]})
        self.assertIsNotNone(comparison)

    def test_genitive_rule_is_an_independent_operation(self) -> None:
        self.assertEqual("bils", _genitive("bil"))
        self.assertEqual("bilens", _genitive("bilen"))
        self.assertEqual("bilars", _genitive("bilar"))
        self.assertEqual("bilarnas", _genitive("bilarna"))
        for already_sibilant in ("hus", "box", "quiz"):
            with self.subTest(form=already_sibilant):
                self.assertEqual(already_sibilant, _genitive(already_sibilant))

    def test_genitive_completion_is_applied_to_each_noun_slot_independently(self) -> None:
        cases = (
            ("lemma", "bil", "sg indef gen", "bils"),
            ("sg_def", "bilen", "sg def gen", "bilens"),
            ("pl_indef", "bilar", "pl indef gen", "bilars"),
            ("pl_def", "bilarna", "pl def gen", "bilarnas"),
        )
        for slot, written_form, wanted_msd, expected_genitive in cases:
            with self.subTest(slot=slot):
                row = InterpretedRow(
                    lemma="bil",
                    pattern="atomic-test",
                    key_forms=(KeyForm(slot, written_form, "atomic-test"),),
                )
                entry = _complete_from_slots(
                    _entry_from_interpreted_row(row),
                    derive_missing_plural_definite=False,
                )
                self.assertIn(
                    (expected_genitive, wanted_msd),
                    {
                        (form.written_form, str(form.msd).casefold())
                        for form in entry.word_forms
                        if form.msd is not None
                    },
                )

    def test_comparison_classifies_more_forms_and_reasons(self) -> None:
        rows, comparisons, summary = generate_noun_artifact([
            {
                "normaliserat_ord": "bil",
                "upos": "NOUN",
                "text": "+en +ar",
                "subnr": 1,
            }
        ])
        self.assertEqual(1, summary["noun_records"])
        self.assertEqual(1, len(rows))
        self.assertEqual("more_forms", comparisons[0]["status"])
        self.assertIn("bils", comparisons[0]["added_forms"])
        self.assertEqual("derived_genitive", comparisons[0]["change_reasons"]["bils"])
        self.assertIn("derived_definite_plural", summary["change_reason_counts"])
        text = render_comparison(summary, comparisons)
        self.assertIn("Fler former: 1", text)
        self.assertIn("stycke=", text)
        self.assertIn("orsaker:", text)

    def test_explicit_and_replacement_operations_are_reported(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "alarmklocka",
            "upos": "NOUN",
            "text": "+n -klockor",
            "stycke": "a·larm|klocka",
        })
        self.assertIsNotNone(row)
        assert comparison is not None
        self.assertEqual("replace_tail", comparison["change_reasons"].get("alarmklockor"))
        self.assertEqual(
            "legacy_malformed_form",
            comparison["removed_form_reasons"].get("alarmklocklockor"),
        )
        self.assertEqual([], comparison["semantic_removed_forms"])

    def test_classifies_legacy_comment_tokens_as_noise(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "ansökan",
            "upos": "NOUN",
            "text": "best. +; i: pl. används: ansökningar",
            "stycke": "an|sök·an",
        })
        self.assertIsNotNone(row)
        assert comparison is not None
        self.assertEqual(["används", "i"], comparison["legacy_noise_removed_forms"])
        self.assertEqual([], comparison["semantic_removed_forms"])

    def test_classifies_truncated_legacy_tokens_as_noise(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "a-kassa",
            "upos": "NOUN",
            "text": "+n a-kassor",
            "stycke": "a-kassa",
        })
        self.assertIsNotNone(row)
        assert comparison is not None
        self.assertEqual(["a"], comparison["legacy_noise_removed_forms"])
        self.assertEqual([], comparison["semantic_removed_forms"])

    def test_classifies_suffix_on_wrong_phrase_word_as_malformed(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "a conto-betalning",
            "upos": "NOUN",
            "text": "+en +ar",
            "stycke": "a conto-be·tal·ning",
        })
        self.assertIsNotNone(row)
        assert comparison is not None
        self.assertEqual(
            ["aar conto-betalning", "aen conto-betalning"],
            comparison["legacy_malformed_removed_forms"],
        )
        self.assertEqual([], comparison["semantic_removed_forms"])

    def test_unsupported_noun_is_preserved_in_comparison(self) -> None:
        rows, comparisons, summary = generate_noun_artifact([
            {
                "normaliserat_ord": "testord",
                "upos": "NOUN",
                "text": "helt okänd notation 123",
                "subnr": 2,
            }
        ])
        self.assertEqual([], rows)
        self.assertEqual("unsupported", comparisons[0]["status"])
        self.assertEqual(1, summary["unsupported_noun_records"])
        self.assertEqual({}, comparisons[0]["change_reasons"])


if __name__ == "__main__":
    unittest.main()
