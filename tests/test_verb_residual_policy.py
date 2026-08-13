from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_residual_policy import interpret_residual_verb_slots


class VerbResidualPolicyTests(unittest.TestCase):
    def parse(self, lemma: str, text: str | None):
        slots = interpret_residual_verb_slots(
            {
                "normaliserat_ord": lemma,
                "upos": "VERB",
                "text": text,
                "stycke": lemma,
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        return slots

    def test_missing_pattern_keeps_only_lemma(self) -> None:
        for lemma in ("förbaske", "lär", "månde", "nåde"):
            with self.subTest(lemma=lemma):
                slots = self.parse(lemma, None)
                self.assertEqual((lemma,), slots.written_forms())

    def test_present_label_assigns_lemma_to_present(self) -> None:
        slots = self.parse("lyster", "pres.")
        self.assertEqual(("lyster",), slots.written_forms())
        self.assertEqual(
            ("lemma", "infinitive", "present"),
            tuple(form.slot for form in slots.forms),
        )

    def test_occasional_present_keeps_both_forms(self) -> None:
        slots = self.parse("torde", "pres. ibl. tör")
        self.assertEqual(("torde", "tör"), slots.written_forms())

    def test_defective_labelled_row_keeps_explicit_supine(self) -> None:
        slots = self.parse(
            "måste",
            "pres. och: pret.; sup. måst; prov. och: finl. inf.",
        )
        self.assertEqual(("måste", "måst"), slots.written_forms())
        self.assertEqual(
            ("lemma", "infinitive", "present", "preterite", "supine"),
            tuple(form.slot for form in slots.forms),
        )

    def test_single_explicit_form_is_kept_without_slot_guess(self) -> None:
        slots = self.parse("må", "måtte")
        self.assertEqual(("må", "måtte"), slots.written_forms())
        self.assertEqual("explicit_additional", slots.forms[-1].slot)

    def test_rejects_multiword_and_affix_entries(self) -> None:
        for lemma in ("ta sig", "-göra", "göra-"):
            with self.subTest(lemma=lemma):
                self.assertIsNone(
                    interpret_residual_verb_slots(
                        {"normaliserat_ord": lemma, "upos": "VERB", "text": None}
                    )
                )


if __name__ == "__main__":
    unittest.main()
