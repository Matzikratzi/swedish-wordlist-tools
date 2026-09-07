from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_migrate_manual_glyph_labels import migrate_payload


class ManualGlyphLabelMigrationTests(unittest.TestCase):
    def test_old_italic_plus_becomes_printed_tilde(self) -> None:
        payload = {"glyphs": [{"label": "+", "style": "italic", "sources": [1]}]}
        migrated, changed = migrate_payload(payload)
        self.assertEqual(changed, 1)
        self.assertEqual(migrated["glyphs"][0]["label"], "~")
        self.assertEqual(migrated["glyphs"][0]["sources"], [1])

    def test_other_special_labels_are_preserved(self) -> None:
        payload = {
            "glyphs": [
                {"label": "¤", "style": "italic"},
                {"label": "·", "style": "bold"},
                {"label": "+", "style": "roman"},
            ]
        }
        migrated, changed = migrate_payload(payload)
        self.assertEqual(changed, 0)
        self.assertEqual([row["label"] for row in migrated["glyphs"]], ["¤", "·", "+"])


if __name__ == "__main__":
    unittest.main()
