from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_left_edge_local_index import LocalExactHit, LocalIndexedGlyph
from swedish_wordlist_tools.ocr_row_finder_one_at_a_time import first_known_row_start
from swedish_wordlist_tools.ocr_row_split_left_support import row_start_geometry


def hit(label: str, *, x: int, top_y: int, baseline: int, steps: int, pixels: int = 8) -> LocalExactHit:
    model = GlyphModel(
        label=label,
        style="unknown",
        pixels=frozenset((i, -1) for i in range(pixels)),
    )
    indexed = LocalIndexedGlyph(
        model=model,
        signature=tuple((1, 0) for _ in range(max(1, steps))),
        anchor_y=-1,
        anchor_x=0,
        end_y=-1 + max(1, steps),
    )
    source_anchor_y = top_y
    source_anchor_x = x
    return LocalExactHit(
        indexed=indexed,
        source_anchor_y=source_anchor_y,
        source_anchor_x=source_anchor_x,
        steps=steps,
        scan_x=x,
    )


class OneRowAtATimeFinderTests(unittest.TestCase):
    def test_leftmost_glyph_on_same_row_establishes_row(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        a = hit("a", x=57, top_y=4, baseline=5, steps=7)
        p = hit("p", x=65, top_y=4, baseline=5, steps=10)
        found = first_known_row_start(
            [p, a],
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=16,
            min_steps=3,
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual("a", found.label)
        self.assertEqual(57, found.x)

    def test_first_physical_row_wins_over_stronger_later_headword(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        continuation = hit("r", x=68, top_y=3, baseline=4, steps=4)
        headword = hit("b", x=57, top_y=10, baseline=11, steps=10)
        found = first_known_row_start(
            [headword, continuation],
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=16,
            min_steps=3,
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual("r", found.label)
        self.assertEqual(3, found.top_y)

    def test_late_fragment_cannot_establish_row(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        late = hit(".", x=83, top_y=1, baseline=2, steps=3)
        real = hit("a", x=57, top_y=4, baseline=5, steps=7)
        found = first_known_row_start(
            [late, real],
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=16,
            min_steps=3,
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual("a", found.label)

    def test_search_stops_after_one_row_distance(self) -> None:
        geometry = row_start_geometry(46, 57, 68)
        later = hit("b", x=57, top_y=17, baseline=18, steps=10)
        found = first_known_row_start(
            [later],
            geometry=geometry,
            previous_break_y=0,
            max_row_distance=16,
            min_steps=3,
        )
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
