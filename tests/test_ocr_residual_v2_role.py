import unittest

from swedish_wordlist_tools.ocr_add_row_residual_glyphs import add_or_merge_glyph


class ResidualV2RoleTests(unittest.TestCase):
    def test_merge_promotes_reviewed_style_to_active_v2_role(self):
        payload = {
            "format": "saol14-manual-glyph-facit-v2",
            "glyphs": [
                {
                    "label": "³",
                    "style": "bold",
                    "role": "unknown",
                    "pixels_relative_to_baseline": [[0, -8], [1, -7]],
                    "sources": [],
                }
            ],
        }
        glyph = {
            "label": "³",
            "style": "bold",
            "pixels_relative_to_baseline": [[0, -8], [1, -7]],
            "sources": [{"page": 9, "column": 0, "row": 19}],
        }

        outcome = add_or_merge_glyph(payload, glyph)

        self.assertEqual(outcome, "merged")
        self.assertEqual(payload["glyphs"][0]["role"], "bold")
        self.assertEqual(len(payload["glyphs"][0]["sources"]), 1)

    def test_added_v2_model_gets_active_role(self):
        payload = {"format": "saol14-manual-glyph-facit-v2", "glyphs": []}
        glyph = {
            "label": "³",
            "style": "bold",
            "pixels_relative_to_baseline": [[0, -8], [1, -7]],
            "sources": [],
        }

        outcome = add_or_merge_glyph(payload, glyph)

        self.assertEqual(outcome, "added")
        self.assertEqual(payload["glyphs"][0]["role"], "bold")


if __name__ == "__main__":
    unittest.main()
