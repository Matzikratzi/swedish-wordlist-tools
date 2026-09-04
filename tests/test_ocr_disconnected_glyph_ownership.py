import threading
import unittest

from swedish_wordlist_tools.ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray, UNASSIGNED_INK


class DisconnectedGlyphOwnershipTests(unittest.TestCase):
    def test_lower_baseline_exact_glyph_reclaims_detached_upper_piece(self):
        width = 12
        height = 12
        owners = PagePixelArray(width=width, height=height, data=bytearray(width * height))
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)

        # A generic disconnected glyph: a 2x2 detached top component and a
        # 2x6 stem.  Baseline is page y=9.
        model_pixels = frozenset(
            {(0, -8), (1, -8), (0, -7), (1, -7)}
            | {(0, y) for y in range(-5, 1)}
            | {(1, y) for y in range(-5, 1)}
        )
        model = GlyphModel(label="i", style="bold", pixels=model_pixels, sources=3)
        placed = {(4 + x, 9 + y) for x, y in model_pixels}
        detached = {(x, y) for x, y in placed if y <= 2}
        stem = placed - detached
        for x, y in detached:
            owners.data[y * width + x] = upper_code
        for x, y in stem:
            owners.data[y * width + x] = lower_code

        context = {
            "row_map": {
                "columns": [{
                    "crop_left": 0,
                    "crop_right": width,
                    "rows": [
                        {"page_top": 1, "page_bottom": 3},
                        {"page_top": 4, "page_bottom": 11},
                    ],
                }]
            },
            "column_content_lefts": {0: 0},
            "pixel_owners": owners,
            "known_glyph_ownership_lock": threading.Lock(),
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
            "quiet_successful_ownership": True,
        }
        state = {
            "column": 0,
            "row": 1,
            "crop_box": (0, 3, width, 11),
            "baseline": 6,
            "fully_exact": False,
        }

        records = repair_lower_row_disconnected_glyphs(context, state, [model])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "lower-from-disconnected-exact-glyph")
        self.assertEqual(records[0]["moved_from_upper"], len(detached))
        self.assertTrue(all(owners.value(x, y) == lower_code for x, y in placed))
        self.assertEqual(context["pixel_owner_revision"], 1)
        self.assertEqual(context["pixel_owner_row_revisions"], {(0, 0): 1, (0, 1): 1})
        self.assertEqual(context["row_map"]["columns"][0]["rows"][0]["page_bottom"], 1)

    def test_partial_model_does_not_claim_component_with_extra_source_ink(self):
        width = 8
        height = 10
        owners = PagePixelArray(width=width, height=height, data=bytearray(width * height))
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)
        model = GlyphModel(
            label="x",
            style="roman",
            pixels=frozenset({(0, -3), (0, -2), (0, 0)}),
            sources=1,
        )
        for x, y, code in [(3, 3, upper_code), (3, 4, upper_code), (3, 6, lower_code), (4, 6, lower_code)]:
            owners.data[y * width + x] = code
        context = {
            "row_map": {"columns": [{"crop_left": 0, "crop_right": width, "rows": [
                {"page_top": 3, "page_bottom": 5}, {"page_top": 6, "page_bottom": 9}
            ]}]},
            "column_content_lefts": {0: 0},
            "pixel_owners": owners,
            "known_glyph_ownership_lock": threading.Lock(),
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
        }
        state = {"column": 0, "row": 1, "crop_box": (0, 3, width, 9), "baseline": 6, "fully_exact": False}

        before = bytes(owners.data)
        records = repair_lower_row_disconnected_glyphs(context, state, [model])

        self.assertEqual(records, [])
        self.assertEqual(bytes(owners.data), before)


if __name__ == "__main__":
    unittest.main()
