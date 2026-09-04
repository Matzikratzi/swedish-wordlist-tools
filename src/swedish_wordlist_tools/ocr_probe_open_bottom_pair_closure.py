from __future__ import annotations

"""Strict observational closure for two adjacent open-bottom row probes."""

from .ocr_benchmark_open_bottom import _probe_page_pixels
from .ocr_open_bottom_probe import probe_open_bottom
from .ocr_probe_open_bottom_batch import _expanded_row_crop
from .ocr_probe_row_glyphs import row_ink


def state_source_page_pixels(state: dict) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    return {
        (left + int(x), top + int(y))
        for x, y in state.get("source_ink_points") or []
    }


def _translated_baseline_hint(state: dict, box: tuple[int, int, int, int]) -> int | None:
    baseline = state.get("baseline")
    if baseline is None:
        return None
    state_top = int((state.get("crop_box") or (0, 0, 0, 0))[1])
    return int(baseline) + state_top - int(box[1])


def probe_pair_closure(
    context: dict,
    upper_position: tuple[int, int],
    upper_state: dict,
    lower_state: dict,
    models,
    *,
    threshold: int = 210,
    baseline_radius: int = 1,
    beam_width: int = 128,
) -> dict:
    """Probe both rows independently, then demand exact two-row pixel closure.

    The ordinary final ownership is used only as a regression oracle.  Closure
    succeeds iff the union of both open-bottom selections equals exactly the
    union of the two ordinary source-ink sets.  Extra pixels are therefore just
    as fatal as missing pixels.
    """
    column, row = map(int, upper_position)
    lower_position = (column, row + 1)

    upper_crop, upper_box = _expanded_row_crop(context, upper_position, upper_state)
    lower_crop, lower_box = _expanded_row_crop(context, lower_position, lower_state)

    upper_result = probe_open_bottom(
        row_ink(upper_crop, threshold=threshold),
        upper_crop.width,
        upper_crop.height,
        models,
        baseline_hint=_translated_baseline_hint(upper_state, upper_box),
        baseline_radius=baseline_radius,
        beam_width=beam_width,
    )
    lower_result = probe_open_bottom(
        row_ink(lower_crop, threshold=threshold),
        lower_crop.width,
        lower_crop.height,
        models,
        baseline_hint=_translated_baseline_hint(lower_state, lower_box),
        baseline_radius=baseline_radius,
        beam_width=beam_width,
    )

    target = state_source_page_pixels(upper_state) | state_source_page_pixels(lower_state)
    selected = _probe_page_pixels(upper_result, upper_box) | _probe_page_pixels(lower_result, lower_box)
    missing = target - selected
    extra = selected - target
    return {
        "closed": bool(target) and not missing and not extra,
        "target_pixels": len(target),
        "selected_pixels": len(selected),
        "missing_pixels": len(missing),
        "extra_pixels": len(extra),
        "missing_x": None if not missing else (min(x for x, _y in missing), max(x for x, _y in missing)),
        "extra_x": None if not extra else (min(x for x, _y in extra), max(x for x, _y in extra)),
        "upper": upper_result,
        "lower": lower_result,
    }
