from __future__ import annotations

"""Explain baseline guesses made by the page-cached fast glyph analyser.

This is deliberately not a second OCR implementation.  It prepares the same
page context, uses the same owned-row crop and runs the same page-cached exact
cover as ``ocr_fast_regression_scan``.  The extra output only inspects the
first-anchor candidates from that fast path so a miss can be debugged without
falling back to the exhaustive analyser.
"""

import argparse
from pathlib import Path

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_fast_regression_scan import _fast_only_analyser
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_probe_row_glyphs import row_ink


def _first_anchor_baselines(ink, width: int, height: int, models) -> dict:
    """Inspect exactly the candidate order used at the fast path's first anchor."""
    if not ink:
        return {"anchor": None, "candidates": [], "counts": {}}

    page_candidates = cached._bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    anchor_x = min(x for x, _y in ink)
    anchor_y = min(y for x, y in ink if x == anchor_x)
    remaining = frozenset(ink)

    counts = {
        "models": 0,
        "left_pixels": 0,
        "x_bounds_reject": 0,
        "baseline_bounds_reject": 0,
        "raster_reject": 0,
        "anchor_matches": 0,
    }
    candidates = []
    for model, min_x, left_pixels in cached._iter_candidates(
        page_candidates,
        first_glyph=True,
        previous_style=None,
        row_kind=row_kind,
        leading_homonym_seen=False,
        baseline_established=False,
    ):
        counts["models"] += 1
        x0 = anchor_x - min_x
        if x0 < 0 or x0 + model.width > width:
            counts["x_bounds_reject"] += len(left_pixels)
            continue
        for _mx, my in left_pixels:
            counts["left_pixels"] += 1
            baseline = anchor_y - my
            if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                counts["baseline_bounds_reject"] += 1
                continue
            placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
            if not placed.issubset(remaining):
                counts["raster_reject"] += 1
                continue
            counts["anchor_matches"] += 1
            candidates.append(
                {
                    "label": model.label,
                    "style": str(model.style),
                    "baseline": int(baseline),
                    "x": int(x0),
                    "pixels": len(placed),
                    "leading_homonym": bool(
                        row_kind == "homonym" and priority._is_homonym_model(model)
                    ),
                }
            )

    return {
        "anchor": (anchor_x, anchor_y),
        "row_kind": row_kind,
        "candidates": candidates,
        "counts": counts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Debug the baseline candidates considered by the real page-cached fast OCR path."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    cached.bind_page_candidates(context, models)

    position = (args.column, args.row)
    if position not in context["positions"]:
        raise ValueError(f"row not found: page={args.page} column={args.column} row={args.row}")

    priority.set_row_priority_hint(priority.classify_row_start(context, position))
    with _fast_only_analyser():
        state = page_editor._load_owned_row_state(context, position, models)

    # _load_owned_row_state intentionally returns the analyser summary rather
    # than its private thresholded raster.  Recreate exactly the same ink from
    # the returned owned crop; this is the same row_ink() operation used by
    # analyse_row_fast_only, not a second OCR path.
    crop = state["crop"]
    ink = row_ink(crop, threshold=int(context["threshold"]))
    diag = _first_anchor_baselines(
        ink,
        crop.width,
        crop.height,
        models,
    )

    print(
        f"fast-baseline-debug: page={args.page} column={args.column} row={args.row} "
        f"row_kind={diag.get('row_kind')} crop_box={state.get('crop_box')} "
        f"row_page={state.get('row_page_top')}..{state.get('row_page_bottom')} "
        f"effective_bottom={state.get('effective_row_page_bottom')}"
    )
    print(
        f"fast-baseline-debug: exact={bool(state.get('fully_exact'))} "
        f"covered={int(state.get('covered_pixels') or 0)}/{int(state.get('source_pixels') or 0)} "
        f"chosen_baseline={state.get('baseline')} anchor={diag.get('anchor')}"
    )
    counts = diag.get("counts", {})
    print(
        "fast-baseline-debug: first-anchor "
        + " ".join(f"{key}={value}" for key, value in counts.items())
    )

    candidates = diag.get("candidates", [])
    if not candidates:
        print("fast-baseline-debug: no first-glyph candidate survives raster matching")
    else:
        by_baseline: dict[int, list[dict]] = {}
        for candidate in candidates:
            by_baseline.setdefault(int(candidate["baseline"]), []).append(candidate)
        for baseline in sorted(by_baseline):
            rows = by_baseline[baseline]
            labels = ", ".join(
                f"{row['label']!r}/{row['style']}@x{row['x']}[{row['pixels']}]"
                + ("(homonym)" if row["leading_homonym"] else "")
                for row in rows[:12]
            )
            suffix = "" if len(rows) <= 12 else f", ... +{len(rows)-12}"
            print(
                f"fast-baseline-debug: baseline={baseline} "
                f"first-glyph-candidates={len(rows)}: {labels}{suffix}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
