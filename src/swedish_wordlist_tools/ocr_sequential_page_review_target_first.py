from __future__ import annotations

from typing import Any

from PIL import Image

from . import ocr_prepare_sequential_page as sequential_page


def _target_first_line_context(
    page: Image.Image,
    line_context: dict[str, Any] | None,
    threshold: int,
) -> dict[str, Any] | None:
    """Analyse only the target row unless ink really crosses into a neighbour.

    The physical-line discovery may retain up to five source rows, but the
    expensive glyph matcher should normally see only the middle/target row.
    Immediate neighbours are activated only when one 4-connected black source
    component owns pixels on both sides of the target/neighbour Voronoi boundary.
    An outer row (-2/+2) can only be activated after its nearer neighbour has
    already been activated and the same geometric crossing test requires it.

    Detached accents that still lie inside the target row's own Tesseract band
    (plus the ordinary vertical crop padding) remain available without opening a
    neighbouring physical row. Separated ink beyond a white gap is therefore not
    a review candidate for the target row.
    """
    if not line_context or not line_context.get("bands_page"):
        return line_context

    bands = list(line_context["bands_page"])
    target = int(line_context["target_index"])
    column_left = int(line_context.get("column_left", 0))
    column_right = int(line_context.get("column_right", page.width))
    active = {target}

    upper = target - 1
    if upper >= 0 and sequential_page._rows_share_black_component(
        page, bands, upper, target, column_left, column_right, threshold
    ):
        active.add(upper)
        upper_outer = target - 2
        if upper_outer >= 0 and sequential_page._rows_share_black_component(
            page, bands, upper_outer, upper, column_left, column_right, threshold
        ):
            active.add(upper_outer)

    lower = target + 1
    if lower < len(bands) and sequential_page._rows_share_black_component(
        page, bands, target, lower, column_left, column_right, threshold
    ):
        active.add(lower)
        lower_outer = target + 2
        if lower_outer < len(bands) and sequential_page._rows_share_black_component(
            page, bands, lower, lower_outer, column_left, column_right, threshold
        ):
            active.add(lower_outer)

    indices = sorted(active)
    selected = [dict(bands[i]) for i in indices]
    return {
        **line_context,
        "bands_page": selected,
        "target_index": indices.index(target),
        "source_band_indices": indices,
        "neighbor_support_rows": [i for i in indices if abs(i - target) == 1],
        "outer_support_rows": [i for i in indices if abs(i - target) == 2],
        "analysis_window": "target-first-connected-neighbours",
    }


def main() -> int:
    # Patch the geometry policy before importing the persistent wrapper. The
    # original prepare_page function looks up _active_line_context dynamically,
    # so its established Tesseract/JSONL/debug format remains unchanged.
    sequential_page._active_line_context = _target_first_line_context

    from . import ocr_sequential_page_review_persistent as persistent

    # Never reuse caches produced by the older always-+/-1-row policy.
    persistent.PREP_CACHE_VERSION = "saol-page-prep-target-first-v1"
    persistent.ANALYSIS_CACHE_VERSION = "saol-row-analysis-target-first-v1"
    return persistent.main()


if __name__ == "__main__":
    raise SystemExit(main())
