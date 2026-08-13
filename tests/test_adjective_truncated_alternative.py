from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_slots import interpret_simple_adjective_slots


class AdjectiveTruncatedAlternativeTests(unittest.TestCase):
    def test_preserves_complete_near_comparison_forms(self) -> None:
        record = {
            "normaliserat_ord": "nära",
            "upos": "ADJ",
            "text": "komp. närmare el. närmre, superl. närmast el. närm",
            "stycke": "nära",
        }
        slots = interpret_simple_adjective_slots(record)
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("nära", "närmare", "närmre", "närmast"),
            slots.written_forms(),
        )

    def test_does_not_guess_completion_of_truncated_fragment(self) -> None:
        record = {
            "normaliserat_ord": "nära",
            "upos": "ADJ",
            "text": "komp. närmare el. närmre, superl. närmast el. närm",
            "stycke": "nära",
        }
        slots = interpret_simple_adjective_slots(record)
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertNotIn("närm", slots.written_forms())
        self.assertNotIn("närmsta", slots.written_forms())


if __name__ == "__main__":
    unittest.main()
