from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_sequential_page_review_cached import _group_paths


class CachedSequentialPageReviewTests(unittest.TestCase):
    def _write_debug(self, root: Path, name: str, bbox, target_index: int, source_band_indices):
        path = root / name
        path.write_text(
            json.dumps(
                {
                    "page_word_bbox": bbox,
                    "five_row_context": {
                        "target_index": target_index,
                        "source_band_indices": source_band_indices,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_groups_words_that_share_one_physical_row_raster(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = self._write_debug(root, "a.json", [0, 100, 220, 60], 1, [4, 5, 6])
            b = self._write_debug(root, "b.json", [0, 100, 220, 60], 1, [4, 5, 6])
            c = self._write_debug(root, "c.json", [0, 140, 220, 60], 1, [5, 6, 7])

            groups = _group_paths([a, b, c])

            self.assertEqual(len(groups), 2)
            self.assertEqual([path for _, path in groups[0]], [a, b])
            self.assertEqual([path for _, path in groups[1]], [c])
            self.assertEqual([index for index, _ in groups[0]], [0, 1])
            self.assertEqual([index for index, _ in groups[1]], [2])

    def test_does_not_merge_same_crop_with_different_target_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = self._write_debug(root, "a.json", [0, 100, 220, 80], 1, [3, 4, 5, 6])
            b = self._write_debug(root, "b.json", [0, 100, 220, 80], 2, [3, 4, 5, 6])

            groups = _group_paths([a, b])

            self.assertEqual(len(groups), 2)


if __name__ == "__main__":
    unittest.main()
