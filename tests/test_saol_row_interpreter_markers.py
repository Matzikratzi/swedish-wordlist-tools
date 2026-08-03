from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_row_interpreter import interpret_noun_row


class SaolRowInterpreterMarkerTests(unittest.TestCase):
    @staticmethod
    def record(lemma: str, pattern: str, stycke: str = "") -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "stycke": stycke,
            "ordkl": "s.",
            "upos": "NOUN",
        }

    def test_h_marks_plural_alternative_without_becoming_a_form(self) -> None:
        row = interpret_noun_row(self.record("airbag", "+en; pl. +ar H +s"))
        self.assertIsNotNone(row)
        forms = {form.written_form for form in row.key_forms} if row else set()
        self.assertNotIn("H", forms)
        self.assertEqual(
            {"airbagar", "airbags"},
            {
                form.written_form
                for form in (row.key_forms if row else ())
                if form.slot == "pl_indef"
            },
        )

    def test_plural_use_comment_does_not_emit_control_words(self) -> None:
        row = interpret_noun_row(
            self.record("anmodan", "best. +; i: pl. används: anmodanden")
        )
        self.assertIsNotNone(row)
        forms = {form.written_form for form in row.key_forms} if row else set()
        self.assertNotIn("i:", forms)
        self.assertNotIn("används:", forms)
        self.assertEqual("anmodanden", row.form("pl_indef") if row else None)

    def test_colloquial_alternative_stays_in_singular_slot(self) -> None:
        row = interpret_noun_row(
            self.record("fredag", "+en el. vard. -dan; pl. +ar", "fre|dag")
        )
        self.assertIsNotNone(row)
        self.assertEqual(
            {"fredagen", "fredan"},
            {
                form.written_form
                for form in (row.key_forms if row else ())
                if form.slot == "sg_def"
            },
        )


if __name__ == "__main__":
    unittest.main()
