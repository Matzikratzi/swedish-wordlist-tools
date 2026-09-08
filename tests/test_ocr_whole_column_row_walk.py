from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_local_index import LocalExactHit, LocalIndexedGlyph
from swedish_wordlist_tools.ocr_row_split_left_support import row_start_geometry
from swedish_wordlist_tools.ocr_whole_column_row_walk import walk_row_starts


def model(label: str, *, min_y: int = -3, max_y: int = 2) -> GlyphModel:
    return GlyphModel(label=label, style="unknown", pixels=frozenset({(0, y) for y in range(min_y, max_y + 1)}))


def hit(glyph: GlyphModel, *, x: int, top_y: int, baseline: int, steps: int = 5) -> LocalExactHit:
    anchor_y = min(y for _x, y in glyph.pixels)
    indexed = LocalIndexedGlyph(model=glyph, signature=((1, 0),), anchor_y=anchor_y, anchor_x=0, end_y=anchor_y + 1)
    return LocalExactHit(indexed=indexed, source_anchor_y=baseline + anchor_y, source_anchor_x=x, steps=steps, scan_x=x)


class WholeColumnRowWalkTest(unittest.TestCase):
    def test_walks_consecutive_rows_without_presegmented_boxes(self):
        a = model("a")
        b = model("b")
        geometry = row_start_geometry(46, 57, 68)
        rows = walk_row_starts([hit(a, x=57, top_y=7, baseline=10), hit(b, x=57, top_y=24, baseline=27)], models=[a, b], geometry=geometry, start_y=0, end_y=40, max_row_distance=24, min_steps=3)
        self.assertEqual(["a", "b"], [row.start.label for row in rows])

    def test_deep_facit_glyph_cannot_make_walker_skip_next_row(self):
        a = model("a")
        deep = model("deep", min_y=-3, max_y=20)
        b = model("b")
        geometry = row_start_geometry(46, 57, 68)
        rows = walk_row_starts([hit(a, x=57, top_y=7, baseline=10), hit(b, x=57, top_y=21, baseline=24)], models=[a, deep, b], geometry=geometry, start_y=0, end_y=40, max_row_distance=24, min_steps=3)
        self.assertEqual([10, 24], [row.start.baseline for row in rows])

    def test_same_baseline_hit_is_not_mistaken_for_next_row(self):
        a = model("a")
        same = model("s")
        b = model("b")
        geometry = row_start_geometry(46, 57, 68)
        rows = walk_row_starts([hit(a, x=57, top_y=7, baseline=10), hit(same, x=68, top_y=9, baseline=10), hit(b, x=57, top_y=24, baseline=27)], models=[a, same, b], geometry=geometry, start_y=0, end_y=40, max_row_distance=24, min_steps=3)
        self.assertEqual([10, 27], [row.start.baseline for row in rows])

    def test_fake_lower_baseline_inside_establishing_glyph_extent_is_suppressed(self):
        a = model("a", min_y=-7, max_y=2)
        accent = model("accent", min_y=-9, max_y=-6)
        b = model("b", min_y=-7, max_y=2)
        geometry = row_start_geometry(46, 57, 68)
        rows = walk_row_starts(
            [
                hit(a, x=59, top_y=86, baseline=93, steps=7),
                hit(accent, x=68, top_y=87, baseline=96, steps=3),
                hit(b, x=58, top_y=101, baseline=108, steps=8),
            ],
            models=[a, accent, b],
            geometry=geometry,
            start_y=82,
            end_y=120,
            max_row_distance=24,
            min_steps=3,
            vertical_slack=1,
        )
        self.assertEqual([93, 108], [row.start.baseline for row in rows])
        self.assertGreater(rows[0].next_search_y, 87)
        self.assertLessEqual(rows[0].next_search_y, 101)

    def test_late_apne_fragment_does_not_create_shadow_row(self):
        mark = model("mark")
        a = model("a")
        geometry = row_start_geometry(46, 57, 68)
        rows = walk_row_starts([hit(mark, x=83, top_y=4, baseline=7, steps=8), hit(a, x=57, top_y=7, baseline=10, steps=7)], models=[mark, a], geometry=geometry, start_y=0, end_y=20, max_row_distance=16, min_steps=3)
        self.assertEqual(1, len(rows))
        self.assertEqual("a", rows[0].start.label)
        self.assertEqual(57, rows[0].start.x)


if __name__ == "__main__":
    unittest.main()
