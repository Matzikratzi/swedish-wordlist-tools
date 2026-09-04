from __future__ import annotations

"""Observe whether slow rows meet the following row on adjacent page scanlines."""

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _page_ink(state: dict) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    return {
        (left + int(x), top + int(y))
        for x, y in state.get("source_ink_points") or []
    }


def y_adjacency(upper_state: dict, lower_state: dict) -> dict:
    upper = _page_ink(upper_state)
    lower = _page_ink(lower_state)
    if not upper or not lower:
        return {
            "upper_bottom_y": None,
            "lower_at_y_plus_1": 0,
            "same_x": 0,
            "adjacent_x": 0,
            "upper_bottom_pixels": 0,
        }

    y = max(py for _px, py in upper)
    upper_x = {px for px, py in upper if py == y}
    lower_x = {px for px, py in lower if py == y + 1}
    same_x = upper_x & lower_x
    adjacent_x = {
        x
        for x in upper_x
        if (x - 1 in lower_x) or (x in lower_x) or (x + 1 in lower_x)
    }
    return {
        "upper_bottom_y": y,
        "lower_at_y_plus_1": len(lower_x),
        "same_x": len(same_x),
        "adjacent_x": len(adjacent_x),
        "upper_bottom_pixels": len(upper_x),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "For slow OCR rows, test whether the upper row's lowest owned ink scanline "
            "is followed immediately by lower-row owned ink at y+1."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--slow-row-seconds", type=float, default=0.5)
    args = ap.parse_args()
    if args.slow_row_seconds < 0:
        raise ValueError("--slow-row-seconds must be >= 0")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    monsters = 0
    any_y1 = 0
    same_x_rows = 0
    adjacent_x_rows = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        positions = list(context["positions"])
        posset = set(positions)
        cache: dict[tuple[int, int], dict] = {}

        def load(position: tuple[int, int]) -> tuple[dict, float]:
            if position in cache:
                return cache[position], 0.0
            started = perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            elapsed = perf_counter() - started
            cache[position] = state
            return state, elapsed

        for position in positions:
            column, row = map(int, position)
            lower_position = (column, row + 1)
            if lower_position not in posset:
                continue
            upper_state, elapsed = load(position)
            if elapsed < args.slow_row_seconds:
                continue
            lower_state, _ = load(lower_position)
            info = y_adjacency(upper_state, lower_state)
            monsters += 1
            any_y1 += int(info["lower_at_y_plus_1"] > 0)
            same_x_rows += int(info["same_x"] > 0)
            adjacent_x_rows += int(info["adjacent_x"] > 0)
            print(
                f"monster-y: page {page} column {column} row {row}/{row+1} "
                f"ordinary={elapsed:.3f}s y={info['upper_bottom_y']} "
                f"upper_y_px={info['upper_bottom_pixels']} "
                f"lower_y1_px={info['lower_at_y_plus_1']} "
                f"same_x={info['same_x']} adjacent_x={info['adjacent_x']}",
                flush=True,
            )

    print(
        f"monster-y: monsters={monsters} lower-at-y+1={any_y1}/{monsters} "
        f"same-x={same_x_rows}/{monsters} adjacent-x={adjacent_x_rows}/{monsters}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
