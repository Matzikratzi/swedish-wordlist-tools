from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_fast_grouped_exact import fast_grouped_exact_cover


class _Model:
    def __init__(self, label, pixels):
        self.label = label
        self.pixels = frozenset(pixels)
        self.width = max(x for x, _y in pixels) + 1
        self.min_y = min(y for _x, y in pixels)
        self.max_y = max(y for _x, y in pixels)
        self.sources = 1
        self.style = "roman"


class FastGroupedExactTests(unittest.TestCase):
    def test_refuses_single_group(self):
        model = _Model("a", {(0, 0)})
        self.assertIsNone(fast_grouped_exact_cover({(0, 3)}, 1, 8, [model]))

    def test_group_baseline_guard_is_bounded(self):
        # Two independent groups deliberately sit on very different baselines.
        model = _Model("a", {(0, 0)})
        ink = {(0, 2), (5, 6)}
        self.assertIsNone(
            fast_grouped_exact_cover(ink, 6, 10, [model], baseline_slop=1)
        )


if __name__ == "__main__":
    unittest.main()
