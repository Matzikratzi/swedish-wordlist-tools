from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from swedish_wordlist_tools.ocr_page_analysis_cache import (
    geometry_cache_key,
    glyph_cache_key,
    load_or_compute,
)


class PageAnalysisCacheTests(unittest.TestCase):
    def test_load_or_compute_reuses_cached_value(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)

            def compute():
                calls.append(1)
                return {"rows": [1, 2, 3]}

            first, first_hit, path = load_or_compute(cache_dir, 1, "geometry", "abc", compute)
            second, second_hit, second_path = load_or_compute(cache_dir, 1, "geometry", "abc", compute)

        self.assertEqual(first, {"rows": [1, 2, 3]})
        self.assertEqual(second, first)
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(path, second_path)
        self.assertEqual(len(calls), 1)

    def test_geometry_key_changes_with_image_threshold_or_code(self) -> None:
        image = Image.new("L", (2, 2), 255)
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "seg.py"
            module.write_text("version=1\n", encoding="utf-8")
            key1 = geometry_cache_key(image, threshold=210, segmentation_module_file=str(module))
            image.putpixel((0, 0), 0)
            key2 = geometry_cache_key(image, threshold=210, segmentation_module_file=str(module))
            key3 = geometry_cache_key(image, threshold=211, segmentation_module_file=str(module))
            module.write_text("version=2\n", encoding="utf-8")
            key4 = geometry_cache_key(image, threshold=211, segmentation_module_file=str(module))

        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key2, key3)
        self.assertNotEqual(key3, key4)

    def test_glyph_key_changes_with_facit_or_matcher_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facit = root / "facit.json"
            matcher = root / "matcher.py"
            probe = root / "probe.py"
            row_map = root / "row_map.py"
            facit.write_text("one", encoding="utf-8")
            matcher.write_text("one", encoding="utf-8")
            probe.write_text("one", encoding="utf-8")
            row_map.write_text("one", encoding="utf-8")
            key1 = glyph_cache_key(
                "geometry",
                facit,
                matcher_module_file=str(matcher),
                row_probe_module_file=str(probe),
                row_map_module_file=str(row_map),
            )
            facit.write_text("two", encoding="utf-8")
            key2 = glyph_cache_key(
                "geometry",
                facit,
                matcher_module_file=str(matcher),
                row_probe_module_file=str(probe),
                row_map_module_file=str(row_map),
            )

        self.assertNotEqual(key1, key2)

    def test_glyph_key_changes_with_extra_grouped_matcher_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facit = root / "facit.json"
            matcher = root / "matcher.py"
            probe = root / "probe.py"
            row_map = root / "row_map.py"
            grouped = root / "grouped.py"
            for path in (facit, matcher, probe, row_map, grouped):
                path.write_text("one", encoding="utf-8")

            key1 = glyph_cache_key(
                "geometry",
                facit,
                matcher_module_file=str(matcher),
                row_probe_module_file=str(probe),
                row_map_module_file=str(row_map),
                extra_module_files=(str(grouped),),
            )
            grouped.write_text("two", encoding="utf-8")
            key2 = glyph_cache_key(
                "geometry",
                facit,
                matcher_module_file=str(matcher),
                row_probe_module_file=str(probe),
                row_map_module_file=str(row_map),
                extra_module_files=(str(grouped),),
            )

        self.assertNotEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
