from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_add_row_residual_glyphs import (
    add_or_merge_glyph,
    glyph_from_components,
    parse_glyph_spec,
    residual_component_pixels,
)


class ResidualGlyphFacitTests(unittest.TestCase):
    def test_residual_components_keep_detached_parts_separate(self) -> None:
        components = residual_component_pixels({(1, 1), (1, 2), (4, 0)})
        self.assertEqual(len(components), 2)
        self.assertEqual(components[0], frozenset({(1, 1), (1, 2)}))
        self.assertEqual(components[1], frozenset({(4, 0)}))

    def test_parse_glyph_spec_accepts_u_prefix(self) -> None:
        self.assertEqual(parse_glyph_spec("[=U00,U01"), ("[", (0, 1)))
        self.assertEqual(parse_glyph_spec("'=U02"), ("'", (2,)))

    def test_combined_components_are_normalized_to_left_and_baseline(self) -> None:
        components = [
            frozenset({(10, 3), (10, 4)}),
            frozenset({(12, 2)}),
        ]
        glyph = glyph_from_components(
            "[",
            "roman",
            components,
            (0, 1),
            baseline=5,
            source={"page": 1},
        )
        self.assertEqual(glyph["label"], "[")
        self.assertEqual(glyph["style"], "roman")
        self.assertEqual(
            glyph["pixels_relative_to_baseline"],
            [[0, -2], [0, -1], [2, -3]],
        )

    def test_exact_duplicate_merges_source_instead_of_duplicate_model(self) -> None:
        payload = {
            "glyphs": [
                {
                    "label": "'",
                    "style": "roman",
                    "pixels_relative_to_baseline": [[0, -4]],
                    "sources": [{"page": 1}],
                }
            ]
        }
        duplicate = {
            "label": "'",
            "style": "roman",
            "pixels_relative_to_baseline": [[0, -4]],
            "sources": [{"page": 2}],
        }
        self.assertEqual(add_or_merge_glyph(payload, duplicate), "merged")
        self.assertEqual(len(payload["glyphs"]), 1)
        self.assertEqual(len(payload["glyphs"][0]["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
