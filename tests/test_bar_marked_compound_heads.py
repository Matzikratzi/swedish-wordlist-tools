from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry


class BarMarkedCompoundHeadTests(unittest.TestCase):
    def complete(self, lemma: str, stycke: str, pattern: str):
        record = {
            "normaliserat_ord": lemma,
            "stycke": stycke,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": pattern,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_replaces_head_after_bar(self) -> None:
        entry = self.complete("alarmknapp", "a·larm|knapp", "+n -knappar")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "alarmknapp",
                "alarmknapps",
                "alarmknappn",
                "alarmknappns",
                "alarmknappar",
                "alarmknappars",
                "alarmknapparna",
                "alarmknapparnas",
            },
            set(entry.forms if entry else ()),
        )

    def test_does_not_guess_without_bar(self) -> None:
        entry = self.complete("alarmknapp", "a·larmknapp", "+n -knappar")
        self.assertIsNone(entry)

    def test_uses_last_bar(self) -> None:
        entry = self.complete("storväggklocka", "stor|vägg|klocka", "+n -klockor")
        self.assertIsNotNone(entry)
        self.assertIn("storväggklockor", set(entry.forms if entry else ()))


if __name__ == "__main__":
    unittest.main()
