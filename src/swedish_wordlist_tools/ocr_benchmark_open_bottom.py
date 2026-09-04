from __future__ import annotations

"""A/B benchmark ordinary row analysis against the open-bottom probe.

Observational only: no facit or ownership is changed.  The open-bottom side sees
exactly the same established row top as the ordinary analyser, but its crop is
extended through the following row so the lower boundary is deliberately open.
"""

import argparse
import math
from pathlib import Path
from statistics import median
from time import perf_counter

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_open_bottom_probe import probe_open_bottom
from .ocr_probe_open_bottom_batch import _expanded_row_crop
from .ocr_probe_row_glyphs import row_ink
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    rows = sorted(values)
    index = max(0, min(len(rows) - 1, math.ceil(p * len(rows)) - 1))
    return rows[index]


def _ordinary_page_pixels(state: dict) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    pixels: set[tuple[int, int]] = set()
    for match in state.get("matches") or []:
        pixels.update((left + int(x), top + int(y)) for x, y in match.pixels)
    return pixels


def _probe_page_pixels(result: dict, box: tuple[int, int, int, int]) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, box)
    pixels: set[tuple[int, int]] = set()
    for match in result.get("selected") or []:
        pixels.update((left + int(x), top + int(y)) for x, y in match.pixels)
    return pixels


def _summary(name: str, ordinary: list[float], probe: list[float]) -> str:
    if not ordinary:
        return f"benchmark: {name}: n=0"
    ratios = [p / o for o, p in zip(ordinary, probe) if o > 0]
    return (
        f"benchmark: {name}: n={len(ordinary)} "
        f"ordinary median={median(ordinary):.4f}s p95={_percentile(ordinary, 0.95):.4f}s "
        f"open-bottom median={median(probe):.4f}s p95={_percentile(probe, 0.95):.4f}s "
        f"ratio median={median(ratios):.2f}x p95={_percentile(ratios, 0.95):.2f}x"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="A/B time ordinary and open-bottom analysis on every selected row."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--ordinary-fast-seconds",
        type=float,
        default=0.10,
        help="ordinary rows at or below this time are summarized as fast (default: 0.10)",
    )
    ap.add_argument("--baseline-radius", type=int, default=1)
    ap.add_argument("--beam-width", type=int, default=128)
    ap.add_argument(
        "--print-slower-factor",
        type=float,
        default=1.5,
        help="print rows where open-bottom/ordinary reaches this factor; 0 disables",
    )
    args = ap.parse_args()
    if args.ordinary_fast_seconds < 0:
        raise ValueError("--ordinary-fast-seconds must be >= 0")
    if args.baseline_radius < 0:
        raise ValueError("--baseline-radius must be >= 0")
    if args.beam_width < 1:
        raise ValueError("--beam-width must be >= 1")
    if args.print_slower_factor < 0:
        raise ValueError("--print-slower-factor must be >= 0")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    all_ordinary: list[float] = []
    all_probe: list[float] = []
    fast_ordinary: list[float] = []
    fast_probe: list[float] = []
    exact_same = 0
    exact_total = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        print(f"benchmark: page {page}: {len(context['positions'])} rows", flush=True)
        for position in context["positions"]:
            started = perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            ordinary_elapsed = perf_counter() - started

            crop, box = _expanded_row_crop(context, position, state)
            ink = row_ink(crop, threshold=args.threshold)
            state_top = int((state.get("crop_box") or (0, 0, 0, 0))[1])
            baseline_hint = state.get("baseline")
            if baseline_hint is not None:
                baseline_hint = int(baseline_hint) + state_top - int(box[1])

            started = perf_counter()
            result = probe_open_bottom(
                ink,
                crop.width,
                crop.height,
                models,
                baseline_hint=baseline_hint,
                baseline_radius=args.baseline_radius,
                beam_width=args.beam_width,
            )
            probe_elapsed = perf_counter() - started

            all_ordinary.append(ordinary_elapsed)
            all_probe.append(probe_elapsed)
            if ordinary_elapsed <= args.ordinary_fast_seconds:
                fast_ordinary.append(ordinary_elapsed)
                fast_probe.append(probe_elapsed)

            # This is deliberately a strict observational check, not a claim of
            # pair closure.  For rows ordinary already solves exactly, report
            # whether every ordinary-owned matched pixel is also selected by the
            # open-bottom probe.  Extra probe pixels may belong to the lower row
            # and are not accepted as equivalence here.
            if state.get("fully_exact"):
                exact_total += 1
                ordinary_pixels = _ordinary_page_pixels(state)
                probe_pixels = _probe_page_pixels(result, box)
                same = ordinary_pixels.issubset(probe_pixels)
                exact_same += int(same)
            else:
                same = False

            ratio = probe_elapsed / ordinary_elapsed if ordinary_elapsed > 0 else float("inf")
            if args.print_slower_factor and ratio >= args.print_slower_factor:
                print(
                    f"benchmark-row: page {page} column {position[0]} row {position[1]} "
                    f"ordinary={ordinary_elapsed:.4f}s open-bottom={probe_elapsed:.4f}s "
                    f"ratio={ratio:.2f}x ordinary_exact={int(bool(state.get('fully_exact')))} "
                    f"ordinary_pixels_preserved={int(same)} candidates={result['candidate_count']}",
                    flush=True,
                )

    print(_summary("all", all_ordinary, all_probe), flush=True)
    print(_summary("ordinary-fast", fast_ordinary, fast_probe), flush=True)
    print(
        f"benchmark: ordinary-exact pixel preservation: {exact_same}/{exact_total}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
