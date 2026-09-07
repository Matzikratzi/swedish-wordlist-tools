from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from . import ocr_page_cached_fast_path as page_fast
from . import ocr_priority_fast_path as priority
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _bbox(ink: set[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    if not ink:
        return None
    xs = [x for x, _y in ink]
    ys = [y for _x, y in ink]
    return min(xs), min(ys), max(xs), max(ys)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Trace every page-cached exact-cover call made while loading one OCR review row"
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    position = (args.column, args.row)

    original = page_fast.page_cached_prioritized_fast_exact_cover
    calls: list[dict] = []

    def traced_cover(ink, width, height, call_models, *, max_states=20000):
        ink_set = set(ink)
        row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
        before = priority.priority_stats()
        started = perf_counter()
        result = original(
            ink_set,
            width,
            height,
            call_models,
            max_states=max_states,
        )
        elapsed = perf_counter() - started
        after = priority.priority_stats()
        labels = None
        baseline = None
        if result is not None:
            baseline, selected, _tested = result
            labels = "".join(match.label for match in selected)
        calls.append(
            {
                "elapsed": elapsed,
                "row_kind": row_kind,
                "pixels": len(ink_set),
                "width": int(width),
                "height": int(height),
                "bbox": _bbox(ink_set),
                "placements": int(after.get("placements_tested", 0))
                - int(before.get("placements_tested", 0)),
                "success": result is not None,
                "baseline": baseline,
                "labels": labels,
            }
        )
        return result

    page_fast.page_cached_prioritized_fast_exact_cover = traced_cover
    try:
        started = perf_counter()
        state = load_review_state_pixel_array(context, position, models)
        total = perf_counter() - started
    finally:
        page_fast.page_cached_prioritized_fast_exact_cover = original

    print(
        f"target page={args.page} column={args.column} row={args.row} "
        f"total={total:.6f}s coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )
    print(f"exact_cover_calls={len(calls)}")
    for index, call in enumerate(calls, 1):
        print(
            f"call[{index}] time={call['elapsed']:.6f}s kind={call['row_kind']} "
            f"pixels={call['pixels']} size={call['width']}x{call['height']} "
            f"bbox={call['bbox']} placements={call['placements']} "
            f"success={call['success']} baseline={call['baseline']} labels={call['labels']!r}"
        )
    covered_time = sum(float(call["elapsed"]) for call in calls)
    print(f"exact_cover_time={covered_time:.6f}s")
    print(f"outside_exact_cover_time={max(0.0, total-covered_time):.6f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
