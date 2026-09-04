from __future__ import annotations

"""Compare slow ordinary row analysis with the experimental open-bottom matcher."""

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_open_bottom_probe import probe_open_bottom
from .ocr_probe_row_glyphs import row_ink
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _expanded_row_crop(context: dict, position: tuple[int, int], state: dict):
    """Crop from the established row top through the following row's bottom."""
    column, row_index = map(int, position)
    left, top, right, current_bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    columns = context.get("row_map", {}).get("columns") or []
    bottom = current_bottom
    if 0 <= column < len(columns):
        rows = columns[column].get("rows") or []
        if row_index + 1 < len(rows):
            bottom = max(bottom, int(rows[row_index + 1].get("page_bottom", bottom)))
    gray = context["pixel_gray_page"]
    left = max(0, min(left, gray.width))
    right = max(left, min(right, gray.width))
    top = max(0, min(top, gray.height))
    bottom = max(top, min(bottom, gray.height))
    return gray.crop((left, top, right, bottom)), (left, top, right, bottom)


def _labels(result: dict) -> str:
    return "".join(str(match.label) for match in result.get("selected") or [])


def _format_probe(
    page: int,
    position: tuple[int, int],
    ordinary_elapsed: float,
    probe_elapsed: float,
    box: tuple[int, int, int, int],
    result: dict,
) -> str:
    column, row = position
    baseline = result.get("baseline")
    return (
        f"open-bottom: page {page} column {column} row {row}: "
        f"ordinary={ordinary_elapsed:.3f}s probe={probe_elapsed:.3f}s "
        f"baseline={baseline if baseline is not None else 'none'} "
        f"upper={result['covered_above']}/{result['source_above']} "
        f"below={result['covered_below']}/{result['source_below']} "
        f"total={result['covered_pixels']}/{result['source_pixels']} "
        f"candidates={result['candidate_count']} right={result['rightmost_covered_x']} "
        f"crop_y={box[1]}..{box[3]} labels={_labels(result)!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Run the normal row analyser, then probe only slow rows with a same-baseline "
            "open-bottom exact matcher over the current row plus the following row."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--slow-row-seconds", type=float, default=0.5)
    ap.add_argument("--baseline-radius", type=int, default=1)
    ap.add_argument("--beam-width", type=int, default=128)
    args = ap.parse_args()
    if args.slow_row_seconds < 0:
        raise ValueError("--slow-row-seconds must be >= 0")
    if args.baseline_radius < 0:
        raise ValueError("--baseline-radius must be >= 0")
    if args.beam_width < 1:
        raise ValueError("--beam-width must be >= 1")

    available = _available_pages(args.jsonl)
    pages = _selected_pages(
        available,
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    slow_count = 0
    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        positions = context["positions"]
        print(f"open-bottom: page {page}: {len(positions)} rows", flush=True)
        for index, position in enumerate(positions, start=1):
            started = perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            ordinary_elapsed = perf_counter() - started
            if ordinary_elapsed < args.slow_row_seconds:
                continue
            slow_count += 1
            crop, box = _expanded_row_crop(context, position, state)
            ink = row_ink(crop, threshold=args.threshold)
            crop_top = int(box[1])
            state_top = int((state.get("crop_box") or (0, 0, 0, 0))[1])
            baseline_hint = state.get("baseline")
            if baseline_hint is not None:
                # state baseline is crop-local; expanded crop intentionally keeps
                # the same top today, but translate explicitly so this remains true
                # if the crop helper changes later.
                baseline_hint = int(baseline_hint) + state_top - crop_top
            probe_started = perf_counter()
            result = probe_open_bottom(
                ink,
                crop.width,
                crop.height,
                models,
                baseline_hint=baseline_hint,
                baseline_radius=args.baseline_radius,
                beam_width=args.beam_width,
            )
            probe_elapsed = perf_counter() - probe_started
            print(
                _format_probe(
                    page,
                    position,
                    ordinary_elapsed,
                    probe_elapsed,
                    box,
                    result,
                ),
                flush=True,
            )
        print(f"open-bottom: page {page}: done", flush=True)

    print(f"open-bottom: probed {slow_count} slow rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
