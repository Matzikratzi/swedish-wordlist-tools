from __future__ import annotations

import unittest

from swedish_wordlist_tools.refine_noun_semantic_differences import classify_form
from swedish_wordlist_tools.saol_row_interpreter import interpret_noun_row


class RemainingNounBranchVariantTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str = "") -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke or lemma,
            "upos": "NOUN",
            "ordkl": "s.",
        }

    def test_generates_case_variant_base_from_explicit_colon_branch(self) -> None:
        row = interpret_noun_row(
            self.record(
                "id",
                "id:t el. id:n; pl. id:n _ ID:t el. ID:n; pl. ID:n",
                "<sup>4</sup>id",
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertIn(("lemma", "id"), {(form.slot, form.written_form) for form in row.key_forms})
        self.assertIn(("lemma", "ID"), {(form.slot, form.written_form) for form in row.key_forms})

    def test_generates_case_variant_base_for_hyphen_component(self) -> None:
        row = interpret_noun_row(
            self.record(
                "användar-id",
                "+id:t el. +id:n; pl. +id:n _ +ID:t el. +ID:n; pl. +ID:n",
                "an·vänd·ar-id",
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        forms = {(form.slot, form.written_form) for form in row.key_forms}
        self.assertIn(("lemma", "användar-id"), forms)
        self.assertIn(("lemma", "användar-ID"), forms)
        self.assertIn(("sg_def", "användar-id:t"), forms)
        self.assertIn(("sg_def", "användar-ID:t"), forms)

    def test_classifies_repeated_hyphen_component_without_word_rule(self) -> None:
        row = {
            "lemma": "prefix-xy",
            "notation": "+xy:z _ +XY:z",
        }
        self.assertEqual(
            "legacy_repeated_hyphen_component",
            classify_form(row, "prefix-xyxy"),
        )
        self.assertEqual(
            "legacy_repeated_hyphen_component",
            classify_form(row, "prefix-xyXY"),
        )

    def test_classifies_optional_operation_payload_fragment(self) -> None:
        row = {
            "lemma": "bas",
            "notation": "+a _ +(b)c",
        }
        self.assertEqual(
            "legacy_optional_operation_fragment",
            classify_form(row, "c"),
        )
        self.assertEqual(
            "legacy_optional_operation_fragment",
            classify_form(row, "bc"),
        )
        self.assertEqual("review_required", classify_form(row, "a"))


if __name__ == "__main__":
    unittest.main()
