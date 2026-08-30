from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools import ocr_sequential_page_review_persistent as persistent


class PersistentPageReviewCacheTests(unittest.TestCase):
    def test_area_for_bbox_uses_three_by_four_grid(self) -> None:
        self.assertEqual(persistent._area_for_bbox([0, 0, 10, 10], 300, 400), "c1-r1")
        self.assertEqual(persistent._area_for_bbox([145, 195, 10, 10], 300, 400), "c2-r3")
        self.assertEqual(persistent._area_for_bbox([290, 390, 10, 10], 300, 400), "c3-r4")

    def test_prepare_cache_survives_output_directory_removal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_root = root / "cache"
            jsonl = root / "data.jsonl"
            jsonl.write_text('{}\n', encoding="utf-8")
            calls = []

            def fake_prepare(jsonl_path, page_number, out_dir, **kwargs):
                calls.append((jsonl_path, page_number))
                out_dir.mkdir(parents=True, exist_ok=True)
                debug = {
                    "tesseract": {"raw_bbox": [110, 210, 20, 10]},
                    "page_word_bbox": [100, 200, 100, 40],
                }
                (out_dir / "saol14-word-debug-p00001-0000.json").write_text(
                    json.dumps(debug), encoding="utf-8"
                )
                report = {"page": 1, "page_size": [300, 400], "source": "test"}
                (out_dir / "page-report.json").write_text(json.dumps(report), encoding="utf-8")
                return report

            old_root = persistent._default_cache_root
            old_prepare = persistent._ORIGINAL_PREPARE_PAGE
            try:
                persistent._default_cache_root = lambda: cache_root
                persistent._ORIGINAL_PREPARE_PAGE = fake_prepare

                out1 = root / "out1"
                persistent._cached_prepare_page(jsonl, 1, out1)
                debug1 = json.loads(
                    (out1 / "saol14-word-debug-p00001-0000.json").read_text(encoding="utf-8")
                )
                self.assertEqual(debug1["cache_area"], "c2-r3")
                self.assertTrue((out1 / "area-manifest.json").is_file())

                out2 = root / "out2"
                persistent._cached_prepare_page(jsonl, 1, out2)
                self.assertTrue((out2 / "page-report.json").is_file())
                self.assertEqual(len(calls), 1)
            finally:
                persistent._default_cache_root = old_root
                persistent._ORIGINAL_PREPARE_PAGE = old_prepare

    def test_analysis_cache_reuses_unchanged_area(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            facit = root / "facit.json"
            facit.write_text('{"glyphs": []}\n', encoding="utf-8")
            paths = []
            for i in range(2):
                path = root / f"word-{i}.json"
                path.write_text(
                    json.dumps({
                        "cache_area": "c1-r1",
                        "page_word_bbox": [0, 0, 100, 30],
                        "five_row_context": {"target_index": 1, "source_band_indices": [0, 1, 2]},
                    }),
                    encoding="utf-8",
                )
                paths.append(path)

            calls = []
            old_cache = persistent._ACTIVE_PAGE_CACHE
            old_analysis = persistent._ORIGINAL_ANALYSE_PATHS
            old_key = persistent.row_cached._debug_row_key
            try:
                persistent._ACTIVE_PAGE_CACHE = root / "page-cache"
                persistent._ACTIVE_PAGE_CACHE.mkdir()
                persistent.row_cached._debug_row_key = lambda path: ("shared",)

                def fake_analysis(received, facit_path, workers):
                    calls.append(list(received))
                    return [{"expected": path.name} for path in received]

                persistent._ORIGINAL_ANALYSE_PATHS = fake_analysis
                first = persistent._cached_analyse_paths(paths, facit, 4)
                second = persistent._cached_analyse_paths(paths, facit, 4)
                self.assertEqual(first, second)
                self.assertEqual(len(calls), 1)
            finally:
                persistent._ACTIVE_PAGE_CACHE = old_cache
                persistent._ORIGINAL_ANALYSE_PATHS = old_analysis
                persistent.row_cached._debug_row_key = old_key


if __name__ == "__main__":
    unittest.main()
