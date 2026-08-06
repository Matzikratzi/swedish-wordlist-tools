from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_game_fallback import interpret_playable_verb_slots


class VerbGameFallbackTests(unittest.TestCase):
    def record(self, lemma: str, text: object, ordkl: str = "v.") -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": lemma,
            "upos": "VERB",
            "ordkl": ordkl,
            "homonr": "1",
        }

    def test_keeps_headword_when_pattern_is_missing(self) -> None:
        slots = interpret_playable_verb_slots(self.record("förbaske", None))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("förbaske",), slots.written_forms())
        self.assertEqual("true", slots.metadata["residual_policy"])

    def test_keeps_present_only_headword(self) -> None:
        slots = interpret_playable_verb_slots(self.record("lyster", "pres."))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("lyster",), slots.written_forms())
        self.assertEqual(("lemma", "infinitive", "present"), slots.slots())

    def test_keeps_explicit_present_alternative(self) -> None:
        slots = interpret_playable_verb_slots(self.record("torde", "pres. ibl. tör"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("torde", "tör"), slots.written_forms())
        self.assertEqual(("lemma", "infinitive", "present", "present"), slots.slots())

    def test_keeps_explicit_supine_from_defective_paradigm(self) -> None:
        slots = interpret_playable_verb_slots(
            self.record(
                "måste",
                "pres. och: pret.; sup. måst; prov. och: finl. inf.",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("måste", "måst"), slots.written_forms())
        self.assertEqual(("måst",), slots.forms_for("supine"))
        for marker in ("pres", "och", "pret", "sup", "prov", "finl", "inf"):
            self.assertNotIn(marker, slots.written_forms())

    def test_legacy_fallback_still_keeps_explicit_imperative(self) -> None:
        slots = interpret_playable_verb_slots(
            self.record("lyss", "pres. lyss; imper. lys")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("lyss", "lys"), slots.written_forms())
        self.assertEqual(
            ("lemma", "attested", "attested_present", "attested_imperative"),
            slots.slots(),
        )

    def test_keeps_single_explicit_form(self) -> None:
        slots = interpret_playable_verb_slots(self.record("må", "måtte"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("må", "måtte"), slots.written_forms())
        self.assertEqual("explicit_additional", slots.forms[-1].slot)

    def test_prefers_strict_parser_when_available(self) -> None:
        slots = interpret_playable_verb_slots(self.record("abonnera", "+de +t"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("abonnera", "abonnerade", "abonnerat"), slots.written_forms())
        self.assertNotIn("residual_policy", slots.metadata)
        self.assertNotIn("fallback_kind", slots.metadata)

    def test_excludes_multiword_and_affix_entries_before_parsing(self) -> None:
        for lemma in ("gå an", "-göra", "göra-"):
            with self.subTest(lemma=lemma):
                self.assertIsNone(
                    interpret_playable_verb_slots(self.record(lemma, "gick, gått"))
                )


if __name__ == "__main__":
    unittest.main()
