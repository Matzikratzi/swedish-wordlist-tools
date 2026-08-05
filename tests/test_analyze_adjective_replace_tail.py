from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_replace_tail import replacement_events


class AdjectiveReplaceTailAuditTests(unittest.TestCase):
    def test_lodstreck_is_counted_when_stycke_has_boundary(self) -> None:
        events = replacement_events(
            {
                "normaliserat_ord": "alkoholrelaterad",
                "stycke": "alkohol|relaterad",
                "text": "-relaterat +e",
            }
        )
        self.assertEqual(1, len(events))
        self.assertEqual("lodstreck", events[0]["method"])
        self.assertEqual("alkoholrelaterat", events[0]["result"])
        self.assertEqual("alkohol", events[0]["prefix"])

    def test_fallback_is_counted_without_lodstreck(self) -> None:
        events = replacement_events(
            {
                "normaliserat_ord": "allgod",
                "stycke": "allgod",
                "text": "-gott +a",
            }
        )
        self.assertEqual(1, len(events))
        self.assertEqual("fallback", events[0]["method"])
        self.assertEqual("allgott", events[0]["result"])

    def test_plus_minus_is_not_counted_as_replace_tail(self) -> None:
        events = replacement_events(
            {
                "normaliserat_ord": "reliabel",
                "stycke": "reliabel",
                "text": "+-t reliabla",
            }
        )
        self.assertEqual([], events)

    def test_failed_replacement_is_reported(self) -> None:
        events = replacement_events(
            {
                "normaliserat_ord": "blå",
                "stycke": "blå",
                "text": "-rött +a",
            }
        )
        self.assertEqual("failed", events[0]["method"])
        self.assertEqual("", events[0]["result"])


if __name__ == "__main__":
    unittest.main()
