from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbExpandedGroupTests(unittest.TestCase):
    def record(self, lemma: str, text: str) -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": lemma,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_two_core_groups_before_participle(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "besjunga",
                "besjöng, besjungit, besjungen besjunget besjungna,",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("besjöng",), slots.forms_for("preterite"))
        self.assertEqual(("besjungit",), slots.forms_for("supine"))
        self.assertEqual((), slots.forms_for("present"))

    def test_three_core_groups_before_participle(self) -> None:
        slots = interpret_verb_slots(
            self.record("trä", "trär, trädde, trätt, trädd n. trätt")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("trär",), slots.forms_for("present"))
        self.assertEqual(("trädde",), slots.forms_for("preterite"))
        self.assertEqual(("trätt",), slots.forms_for("supine"))

    def test_alternatives_with_el_and_h(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "tvinga",
                "tvingade H tvang, tvingat H tvungit, tvingad n. tv",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("tvingade", "tvang"), slots.forms_for("preterite"))
        self.assertEqual(("tvingat", "tvungit"), slots.forms_for("supine"))

    def test_present_alternatives_before_preterite_and_supine(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "klä",
                "klär el. åld. kläder, klädde, klätt, klädd n. klät",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("klär", "kläder"), slots.forms_for("present"))
        self.assertEqual(("klädde",), slots.forms_for("preterite"))
        self.assertEqual(("klätt",), slots.forms_for("supine"))


if __name__ == "__main__":
    unittest.main()
