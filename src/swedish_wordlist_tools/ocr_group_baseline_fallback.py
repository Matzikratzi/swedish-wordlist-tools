from __future__ import annotations

from typing import Iterable

from .ocr_glyph_facit_write_redirect import install_facit_write_redirect
from .ocr_glyph_matcher import GlyphModel
from .ocr_page_cached_fast_path import analyse_row_prioritized


install_facit_write_redirect()

# Compatibility hook used by the benchmark layers.  It deliberately starts as
# the same shared parser used by the editor/batch path; benchmark experiments may
# temporarily replace this name and the wrapper below will see that replacement.
analyse_row_exact_grouped = analyse_row_prioritized


def analyse_row_exact_grouped_with_baseline_fallback(
    crop,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> dict:
    """Compatibility wrapper around the shared editor/batch row parser.

    The old editor-only grouped/baseline fallback path intentionally no longer
    selects glyphs.  Interactive review and batch scanning must use the same
    prioritized exact-cover rules so a row cannot acquire a different glyph
    decomposition merely because it was opened in the editor.

    ``analyse_row_exact_grouped`` remains an assignable compatibility hook for
    the existing benchmark stack.  Its default value is the shared parser.
    """
    result = analyse_row_exact_grouped(crop, models, threshold=threshold)
    baseline = result.get("baseline")
    result["baseline_fallbacks"] = []
    result["baseline_segments"] = (
        [{"left": 0, "right": crop.width, "baseline": int(baseline)}]
        if baseline is not None
        else []
    )
    return result
