from __future__ import annotations

from . import ocr_compare_page_text_prefix as base
from . import ocr_glyph_gap_matcher as gap_matcher_module
from . import ocr_probe_row_glyphs_grouped as grouped_probe_module
from .ocr_page_analysis_cache import glyph_cache_key as _glyph_cache_key
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


def _grouped_glyph_cache_key(
    geometry_key,
    facit,
    *,
    matcher_module_file,
    row_probe_module_file,
    row_map_module_file,
):
    return _glyph_cache_key(
        geometry_key,
        facit,
        matcher_module_file=matcher_module_file,
        row_probe_module_file=row_probe_module_file,
        row_map_module_file=row_map_module_file,
        extra_module_files=(
            grouped_probe_module.__file__,
            gap_matcher_module.__file__,
        ),
    )


def main() -> int:
    """Run the existing page comparator with the verified safe-gap matcher."""
    base.analyse_row_exact = analyse_row_exact_grouped
    base.glyph_cache_key = _grouped_glyph_cache_key
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
