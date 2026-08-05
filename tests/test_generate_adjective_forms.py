from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_adjective_forms import generated_row


class GenerateAdjectiveFormsTests(unittest.TestCase):
    def test_generation_uses_stycke_bar_once(self) -> None:
        row = generated_row({
            "normaliserat_ord": "förstfödd",
            "homonr": "1",
            "ordkl": "adj. <i>-fött +a</i>",
            "stycke": "först|född",
            "text": "-fött +a",
            "upos": "ADJ",
            "subnr": 25621,
        })
        assert row is not None
        self.assertEqual(
            ["förstfödd", "förstfött", "förstfödda"],
            [form["written_form"] for form in row["forms"]],
        )
        self.assertEqual(
            ["lemma", "replace_tail", "append"],
            [form["provenance"] for form in row["forms"]],
        )

    def test_regular_forms_get_operation_provenance(self) -> None:
        row = generated_row({
            "normaliserat_ord": "glad",
            "homonr": "1",
            "ordkl": "adj. <i>+t +a</i>",
            "stycke": "glad",
            "text": "+t +a",
            "upos": "ADJ",
            "subnr": 1,
        })
        assert row is not None
        self.assertEqual(
            ["glad", "glatt", "glada"],
            [form["written_form"] for form in row["forms"]],
        )
        self.assertEqual(
            ["lemma", "append", "append"],
            [form["provenance"] for form in row["forms"]],
        )

    def test_generation_applies_documented_source_correction(self) -> None:
        row = generated_row({
            "normaliserat_ord": "anhörig",
            "homonr": "1",
            "ordkl": "adj. <i>pl. -a</i>",
            "stycke": "an|hör·ig",
            "text": "pl. -a",
            "upos": "ADJ",
            "subnr": 442734,
        })
        assert row is not None
        self.assertTrue(row["source_correction_applied"])
        self.assertEqual("pl. +a", row["effective_notation"])
        self.assertEqual(
            ["anhörig", "anhöriga"],
            [form["written_form"] for form in row["forms"]],
        )
        self.assertEqual(
            ["lemma", "append"],
            [form["provenance"] for form in row["forms"]],
        )


if __name__ == "__main__":
    unittest.main()
