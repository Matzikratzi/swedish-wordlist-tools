from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import ocr_group_baseline_fallback as fallback
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Trace baseline fallback cost for one OCR row")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)

    timings: dict[str, list[float]] = {"anchor_candidates": [], "select_at_baseline": [], "anchor_missing_baseline": []}
    originals = {
        "_baseline_anchor_candidates": fallback._baseline_anchor_candidates,
        "_select_at_baseline": fallback._select_at_baseline,
        "_anchor_missing_baseline": fallback._anchor_missing_baseline,
    }

    def timed_anchor_candidates(*a, **kw):
        started = time.perf_counter()
        result = originals["_baseline_anchor_candidates"](*a, **kw)
        elapsed = time.perf_counter() - started
        timings["anchor_candidates"].append(elapsed)
        print(f"fallback anchor_candidates: {elapsed:.6f}s candidates={len(result)}")
        return result

    def timed_select(*a, **kw):
        started = time.perf_counter()
        result = originals["_select_at_baseline"](*a, **kw)
        elapsed = time.perf_counter() - started
        timings["select_at_baseline"].append(elapsed)
        baseline = kw.get("baseline", a[4] if len(a) > 4 else None)
        print(f"fallback select_at_baseline: {elapsed:.6f}s baseline={baseline} selected={len(result)}")
        return result

    def timed_missing(*a, **kw):
        started = time.perf_counter()
        result = originals["_anchor_missing_baseline"](*a, **kw)
        elapsed = time.perf_counter() - started
        timings["anchor_missing_baseline"].append(elapsed)
        print(
            f"fallback anchor_missing_baseline: {elapsed:.6f}s "
            f"baseline={result.get('baseline')} anchor={result.get('baseline_anchor')!r}"
        )
        return result

    fallback._baseline_anchor_candidates = timed_anchor_candidates
    fallback._select_at_baseline = timed_select
    fallback._anchor_missing_baseline = timed_missing
    try:
        started = time.perf_counter()
        state = load_review_state_pixel_array(context, (args.column, args.row), models)
        total = time.perf_counter() - started
    finally:
        for name, original in originals.items():
            setattr(fallback, name, original)

    print(
        f"target page={args.page} column={args.column} row={args.row} total={total:.6f}s "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )
    for key, values in timings.items():
        print(
            f"stage {key}: calls={len(values)} total={sum(values):.6f}s "
            f"each={','.join(f'{value:.6f}' for value in values) if values else '-'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
