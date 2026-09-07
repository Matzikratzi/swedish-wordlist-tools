from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_row_boundary_corrections import (
    BoundaryCorrectionStore,
    apply_boundary_corrections,
    find_boundary_correction,
    page_digest,
)


def _models():
    return [
        GlyphModel(
            "A",
            "roman",
            frozenset({(0, -4), (0, -3), (0, -2), (0, -1), (0, 0), (1, 0)}),
            2,
        ),
        GlyphModel(
            "B",
            "roman",
            frozenset({(0, -3), (1, -3), (0, -2), (1, -2), (0, -1), (1, 0)}),
            2,
        ),
    ]


def _case():
    image = Image.new("L", (20, 16), 255)
    # A belongs to the upper row. Its two lowest raster levels y=8,9 lie below
    # the preliminary cut at 8, so they contaminate the lower crop.
    upper = {(2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (3, 9)}
    # B belongs to the lower row and starts immediately at y=10. Thus the true
    # straight cut is between y=9 and y=10: upper y < 10, lower y >= 10.
    lower = {(10, 10), (11, 10), (10, 11), (11, 11), (10, 12), (11, 13)}
    for point in upper | lower:
        image.putpixel(point, 0)
    row_map = {
        "columns": [
            {
                "column": 0,
                "left": 0,
                "right": 20,
                "rows": [
                    {"index": 0, "page_top": 0, "page_bottom": 8, "center_y": 3.5, "crop_left": 0, "crop_right": 20},
                    {"index": 1, "page_top": 8, "page_bottom": 16, "center_y": 11.5, "crop_left": 0, "crop_right": 20},
                ],
            }
        ]
    }
    return image, row_map


class RowBoundaryCorrectionTests(unittest.TestCase):
    def test_unique_glyph_evidence_moves_touching_boundary(self) -> None:
        image, row_map = _case()
        correction = find_boundary_correction(
            image,
            row_map,
            0,
            0,
            _models(),
            threshold=210,
            max_shift=4,
            source_digest_value=page_digest(image),
            page_number=1,
        )

        self.assertIsNotNone(correction)
        self.assertEqual(correction["original_boundary"], 8)
        self.assertEqual(correction["corrected_boundary"], 10)
        self.assertEqual(correction["shift"], 2)
        self.assertGreater(correction["before"]["unmatched"], correction["after"]["unmatched"])
        self.assertEqual(correction["after"]["unmatched"], 0)

    def test_applied_boundary_is_one_straight_exclusive_cut(self) -> None:
        image, row_map = _case()
        correction = find_boundary_correction(
            image, row_map, 0, 0, _models(), source_digest_value=page_digest(image), page_number=1
        )
        corrected = apply_boundary_corrections(row_map, [correction])
        upper, lower = corrected["columns"][0]["rows"]

        self.assertEqual(upper["page_bottom"], 10)
        self.assertEqual(lower["page_top"], 10)
        self.assertEqual(upper["page_bottom"], lower["page_top"])
        # PIL/our crop convention makes this exactly the desired ownership:
        # upper gets y<=9 and lower gets y>=10, with neither overlap nor gap.
        self.assertLess(9, lower["page_top"] + 1)

    def test_correction_is_persistent_and_not_keyed_by_facit_generation(self) -> None:
        image, row_map = _case()
        digest = page_digest(image)
        correction = find_boundary_correction(
            image,
            row_map,
            0,
            0,
            _models(),
            source_digest_value=digest,
            page_number=1,
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "boundaries.json"
            first = BoundaryCorrectionStore(path)
            first.put(correction)

            second = BoundaryCorrectionStore(path)
            loaded = second.get(
                source_digest=digest,
                page_number=1,
                threshold=210,
                column=0,
                upper_row=0,
            )
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["corrected_boundary"], 10)
            self.assertIn("evidence_facit_digest", loaded)

    def test_ambiguous_equally_good_moved_boundaries_are_not_learned(self) -> None:
        image = Image.new("L", (20, 18), 255)
        # Put complete glyphs far from a broad blank inter-row gap. Moving the
        # cut inside that blank space gives several equally good candidates and
        # therefore must not create a learned correction.
        upper = {(2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (3, 6)}
        lower = {(10, 12), (11, 12), (10, 13), (11, 13), (10, 14), (11, 15)}
        for point in upper | lower:
            image.putpixel(point, 0)
        row_map = {
            "columns": [{"column": 0, "left": 0, "right": 20, "rows": [
                {"index": 0, "page_top": 0, "page_bottom": 9, "center_y": 4.0},
                {"index": 1, "page_top": 9, "page_bottom": 18, "center_y": 13.0},
            ]}]
        }
        correction = find_boundary_correction(image, row_map, 0, 0, _models(), max_shift=3)
        self.assertIsNone(correction)


if __name__ == "__main__":
    unittest.main()
