from __future__ import annotations

"""Run the normal glyph editor with the real fast-path baseline guess overlaid.

The editor remains the existing page-pixel-array editor.  For each displayed
row we additionally run exactly the same fast-only owned-row analysis used by
ocr_fast_regression_scan, inspect its first-anchor baseline candidates, and
show an unambiguous baseline even when the full exact cover fails.
"""

import html

from . import ocr_review_page_pixel_array_glyphs_html as editor
from . import ocr_priority_fast_path as priority
from .ocr_fast_baseline_debug import _first_anchor_baselines
from .ocr_fast_regression_scan import _fast_only_analyser


_original_load = editor.load_review_state_pixel_array
_original_render = editor.fast.ui.editor.render_html


def _fast_diag(context: dict, position: tuple[int, int], models) -> dict:
    priority.set_row_priority_hint(priority.classify_row_start(context, position))
    with _fast_only_analyser():
        fast_state = editor._load_owned_row_state(context, position, models)

    ink = {(int(x), int(y)) for x, y in fast_state.get("source_ink_points") or []}
    diag = _first_anchor_baselines(
        ink,
        int(fast_state["crop_width"]),
        int(fast_state["crop_height"]),
        models,
    )
    candidates = diag.get("candidates") or []
    baselines = sorted({int(candidate["baseline"]) for candidate in candidates})
    baseline_hint = baselines[0] if len(baselines) == 1 else None
    page_baseline = None
    if baseline_hint is not None:
        page_baseline = int(fast_state["crop_box"][1]) + baseline_hint
    return {
        "exact": bool(fast_state.get("fully_exact")),
        "covered": int(fast_state.get("covered_pixels") or 0),
        "source": int(fast_state.get("source_pixels") or 0),
        "chosen_baseline": fast_state.get("baseline"),
        "baseline_hint": baseline_hint,
        "page_baseline": page_baseline,
        "anchor": diag.get("anchor"),
        "candidate_count": len(candidates),
        "baseline_count": len(baselines),
        "baselines": baselines,
        "counts": diag.get("counts") or {},
        "candidates": candidates,
        "geometry_bottom": int(fast_state.get("row_page_bottom") or 0),
    }


def _load_with_fast_baseline(context: dict, position: tuple[int, int], models):
    # Capture fast-path evidence before the normal editor is allowed to repair
    # ownership or use any slower fallback.  That makes the overlay describe
    # precisely the input on which the regression scanner succeeds or fails.
    fast_diag = _fast_diag(context, position, models)
    state = _original_load(context, position, models)
    state = dict(state)
    state["fast_baseline_debug"] = fast_diag

    page_baseline = fast_diag.get("page_baseline")
    neighbor_top = state.get("neighbor_page_top")
    neighbor_bottom = state.get("neighbor_page_bottom")
    if page_baseline is not None and neighbor_top is not None and neighbor_bottom is not None:
        # Existing editor convention draws support one raster line below the
        # baseline.  Keep that convention, but identify this as FAST explicitly.
        support_page_y = int(page_baseline) + 1
        if int(neighbor_top) <= support_page_y <= int(neighbor_bottom):
            local_y = support_page_y - int(neighbor_top)
            label = f"STÖDLINJE FAST baseline row {position[1]}"
            display = [list(item) for item in state.get("neighbor_row_boundaries") or []]
            if [local_y, label] not in display:
                display.append([local_y, label])
                display.sort(key=lambda item: (int(item[0]), str(item[1])))
            state["neighbor_row_boundaries"] = display
            state["neighbor_display_lines"] = display
    return state


def _render_with_fast_panel(state: dict, message: str = "") -> str:
    document = _original_render(state, message)
    diag = state.get("fast_baseline_debug") or {}
    counts = diag.get("counts") or {}
    candidates = diag.get("candidates") or []
    candidate_text = ", ".join(
        f"{c.get('label')!r}@x{c.get('x')}→b{c.get('baseline')}"
        for c in candidates[:12]
    )
    if len(candidates) > 12:
        candidate_text += f", … +{len(candidates)-12}"
    if not candidate_text:
        candidate_text = "inga"
    panel = (
        "<div style=\"margin:8px 0;padding:8px 10px;border:2px solid #1769d2;"
        "background:#eef5ff;font:13px monospace;white-space:pre-wrap\">"
        "<b>FAST PATH</b>\n"
        f"exact={str(bool(diag.get('exact'))).lower()}  "
        f"covered={diag.get('covered',0)}/{diag.get('source',0)}  "
        f"chosen_baseline={html.escape(str(diag.get('chosen_baseline')))}\n"
        f"anchor={html.escape(str(diag.get('anchor')))}  "
        f"baseline_hint={html.escape(str(diag.get('baseline_hint')))}  "
        f"page_baseline={html.escape(str(diag.get('page_baseline')))}  "
        f"geometry_bottom={html.escape(str(diag.get('geometry_bottom')))}\n"
        f"first-anchor: models={counts.get('models',0)} left_pixels={counts.get('left_pixels',0)} "
        f"baseline_reject={counts.get('baseline_bounds_reject',0)} "
        f"raster_reject={counts.get('raster_reject',0)} matches={counts.get('anchor_matches',0)}\n"
        f"kandidater: {html.escape(candidate_text)}"
        "</div>"
    )
    marker = "<body>"
    if marker in document:
        document = document.replace(marker, marker + panel, 1)
    return document


def main() -> int:
    editor.load_review_state_pixel_array = _load_with_fast_baseline
    editor.fast.ui.editor.render_html = _render_with_fast_panel
    return editor.main()


if __name__ == "__main__":
    raise SystemExit(main())
