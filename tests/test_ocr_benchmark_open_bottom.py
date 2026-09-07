from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_benchmark_open_bottom import (
    _ordinary_page_pixels,
    _percentile,
    _probe_page_pixels,
    _summary,
)
from swedish_wordlist_tools.ocr_glyph_matcher import Match


class OpenBottomBenchmarkTests(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        self.assertEqual(_percentile([1.0, 2.0, 3.0, 4.0], 0.95), 4.0)
        self.assertEqual(_percentile([1.0, 2.0, 3.0, 4.0], 0.50), 2.0)
        self.assertEqual(_percentile([], 0.95), 0.0)

    def test_pixel_translation_uses_each_crop_origin(self):
        match = Match(
            label="a",
            style="roman",
            x=0,
            baseline=5,
            pixels=frozenset({(1, 2), (2, 2)}),
            model_pixels=2,
            sources=1,
        )
        state = {"crop_box": (10, 20, 30, 40), "matches": [match]}
        result = {"selected": [match]}
        self.assertEqual(_ordinary_page_pixels(state), {(11, 22), (12, 22)})
        self.assertEqual(_probe_page_pixels(result, (10, 20, 30, 60)), {(11, 22), (12, 22)})

    def test_summary_reports_separate_timings_and_ratio(self):
        text = _summary("ordinary-fast", [0.04, 0.06], [0.02, 0.03])
        self.assertIn("n=2", text)
        self.assertIn("ordinary median=0.0500s", text)
        self.assertIn("open-bottom median=0.0250s", text)
        self.assertIn("ratio median=0.50x", text)


if __name__ == "__main__":
    unittest.main()
