from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_page_start_geometry import infer_page_start_geometry


class PageStartGeometryTests(unittest.TestCase):
    def test_infers_three_start_bands_from_current_page_rows(self) -> None:
        rows = {}
        reference = []
        starts = [30, 31, 30, 41, 42, 41, 52, 53, 52, 30, 41, 52]
        y = 10
        for start in starts:
            reference.append({"page_top": y, "page_bottom": y + 2})
            rows[y] = {start, start + 2, start + 4}
            rows[y + 1] = {start + 1, start + 3}
            y += 3

        inferred = infer_page_start_geometry(rows, reference, tolerance=4)

        self.assertEqual(len(inferred.centers), 3)
        self.assertTrue(any(abs(center - 30) <= 2 for center in inferred.centers))
        self.assertTrue(any(abs(center - 41) <= 2 for center in inferred.centers))
        self.assertTrue(any(abs(center - 52) <= 2 for center in inferred.centers))
        self.assertEqual(len(inferred.ranges), 3)


if __name__ == "__main__":
    unittest.main()
