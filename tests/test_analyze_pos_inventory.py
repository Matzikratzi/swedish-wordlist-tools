from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_pos_inventory import analyze


class AnalyzePosInventoryTests(unittest.TestCase):
    def test_groups_shared_and_remaining_upos(self) -> None:
        report = analyze([
            {"normaliserat_ord": "bok", "upos": "NOUN", "text": "+en +er"},
            {"normaliserat_ord": "glad", "upos": "ADJ", "text": "+t +a"},
            {"normaliserat_ord": "gå", "upos": "VERB", "text": "gick gått"},
            {"normaliserat_ord": "snabbt", "upos": "ADV", "text": None},
            {"normaliserat_ord": "gärna", "upos": "ADV", "text": "hellre helst"},
            {"normaliserat_ord": "den", "upos": "PRON", "text": "det de"},
        ])

        self.assertEqual(["ADJ", "NOUN", "VERB"], report["shared_inflection_upos"])
        by_upos = {row["upos"]: row for row in report["rows"]}
        self.assertEqual("shared_inflection", by_upos["NOUN"]["status"])
        self.assertEqual("not_yet_audited", by_upos["ADV"]["status"])
        self.assertEqual(2, by_upos["ADV"]["records"])
        self.assertEqual(1, by_upos["ADV"]["with_text"])
        self.assertEqual(1, by_upos["ADV"]["without_text"])
        self.assertEqual(2, report["remaining_records_with_text"])

    def test_49_and_50_character_texts_are_counted_as_truncated(self) -> None:
        report = analyze([
            {"normaliserat_ord": "a", "upos": "ADV", "text": "x" * 49},
            {"normaliserat_ord": "b", "upos": "ADV", "text": "y" * 50},
            {"normaliserat_ord": "c", "upos": "ADV", "text": "z" * 48},
        ])
        row = report["rows"][0]
        self.assertEqual(2, row["truncated"])


if __name__ == "__main__":
    unittest.main()
