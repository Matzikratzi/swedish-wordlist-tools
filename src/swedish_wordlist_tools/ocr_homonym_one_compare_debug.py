from __future__ import annotations

"""Compare current and historical homonym-1 facit models against page pixels.

This is diagnostic only. It does not participate in OCR matching.
"""

import argparse
import json
from collections import deque
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_page1_layout_debug import _load_thresholded_page, detect_page1_layout_details


HOMONYM_PROBE_WIDTH = 12


def _facit_ones(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for glyph in payload.get("glyphs") or []:
        if str(glyph.get("label") or "") != "1":
            continue
        pixels = frozenset(
            (int(x), int(y))
            for x, y in glyph.get("pixels_relative_to_baseline") or []
        )
        if not pixels:
            continue
        out.append(
            {
                "model_id": glyph.get("model_id"),
                "role": glyph.get("role"),
                "style": glyph.get("style"),
                "pixels": pixels,
            }
        )
    return out


def _fmt_points(points: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> str:
    return " ".join(f"({x},{y})" for x, y in sorted(points, key=lambda p: (p[1], p[0])))


def _print_models(name: str, models: list[dict]) -> None:
    print(f"homonym-one-{name}: count={len(models)}")
    for index, model in enumerate(models):
        pixels = model["pixels"]
        xs = [x for x, _y in pixels]
        ys = [y for _x, y in pixels]
        print(
            f"  {name}[{index}] id={model['model_id']!r} role={model['role']!r} "
            f"style={model['style']!r} pixels={len(pixels)} "
            f"x={min(xs)}..{max(xs)} y={min(ys)}..{max(ys)}"
        )
        print(f"    points: {_fmt_points(pixels)}")


def _source_ink(context: dict) -> set[tuple[int, int]]:
    owners = context["pixel_owners"]
    return {
        (x, y)
        for y in range(owners.height)
        for x in range(owners.width)
        if owners.data[y * owners.width + x] != 0
    }


def _first_start_pixel(
    raw: set[tuple[int, int]], *, left: int, right: int, top: int, bottom: int
) -> tuple[int, int] | None:
    for x in range(left, right):
        for y in range(top, bottom):
            if (x, y) in raw:
                return x, y
    return None


def _component8(
    raw: set[tuple[int, int]],
    seed: tuple[int, int],
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
) -> set[tuple[int, int]]:
    q = deque([seed])
    seen = {seed}
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                p = (x + dx, y + dy)
                if p in seen:
                    continue
                px, py = p
                if not (left <= px < right and top <= py < bottom):
                    continue
                if p not in raw:
                    continue
                seen.add(p)
                q.append(p)
    return seen


def _best_against_page(
    model: dict,
    raw: set[tuple[int, int]],
    *,
    baseline: int,
    left: int,
    probe_right: int,
) -> tuple[tuple[int, int, int], int, set[tuple[int, int]], set[tuple[int, int]], set[tuple[int, int]]]:
    pixels = model["pixels"]
    min_x = min(x for x, _y in pixels)
    max_x = max(x for x, _y in pixels)
    min_y = min(y for _x, y in pixels)
    max_y = max(y for _x, y in pixels)
    width = max_x - min_x + 1
    best = None
    for glyph_left in range(left, probe_right - width + 1):
        x0 = glyph_left - min_x
        placed = {(x0 + x, baseline + y) for x, y in pixels}
        bbox_raw = {
            (x, y)
            for x, y in raw
            if glyph_left <= x < glyph_left + width
            and baseline + min_y <= y <= baseline + max_y
        }
        hits = placed & raw
        missing = placed - raw
        extra = bbox_raw - placed
        score = (len(hits), -len(missing), -len(extra))
        candidate = (score, glyph_left, hits, missing, extra)
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return best


def _compare_group(
    name: str,
    models: list[dict],
    raw: set[tuple[int, int]],
    *,
    baseline: int,
    left: int,
    probe_right: int,
) -> None:
    print(f"homonym-one-page-compare-{name}: baseline={baseline}")
    for index, model in enumerate(models):
        score, glyph_left, hits, missing, extra = _best_against_page(
            model,
            raw,
            baseline=baseline,
            left=left,
            probe_right=probe_right,
        )
        print(
            f"  {name}[{index}] id={model['model_id']!r} left={glyph_left} "
            f"hits={len(hits)}/{len(model['pixels'])} missing={len(missing)} extra={len(extra)}"
        )
        if missing:
            normalized_missing = {(x - glyph_left, y - baseline) for x, y in missing}
            print(f"    missing-relative: {_fmt_points(normalized_missing)}")
        if extra:
            normalized_extra = {(x - glyph_left, y - baseline) for x, y in extra}
            print(f"    extra-relative: {_fmt_points(normalized_extra)}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare current/historical homonym-1 facit rasters with page-1 source pixels."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True, help="current/local facit")
    ap.add_argument("--historical-facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--column", type=int, default=1)
    ap.add_argument("--baseline", type=int, default=182)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    current = _facit_ones(args.facit)
    historical = _facit_ones(args.historical_facit)
    _print_models("current", current)
    _print_models("historical", historical)

    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    raw = _source_ink(context)
    thresholded_page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    layout = detect_page1_layout_details(thresholded_page)
    column = layout.columns[args.column - 1]
    search_from = layout.row0_tops[args.column - 1]
    left = int(column.left)
    probe_right = min(int(column.right), left + HOMONYM_PROBE_WIDTH)
    top = max(0, search_from - 1)
    bottom = min(context["pixel_owners"].height, args.baseline + 2)

    seed = _first_start_pixel(raw, left=left, right=probe_right, top=search_from, bottom=bottom)
    print(
        f"homonym-one-source: left={left} probe_right={probe_right} search_from={search_from} "
        f"baseline={args.baseline} seed={seed}"
    )
    window = {(x, y) for x, y in raw if left <= x < probe_right and top <= y < bottom}
    normalized_window = {(x - left, y - args.baseline) for x, y in window}
    print(f"homonym-one-source-window: pixels={len(window)} points={_fmt_points(normalized_window)}")

    if seed is not None:
        component = _component8(
            raw,
            seed,
            left=left,
            right=probe_right,
            top=top,
            bottom=bottom,
        )
        min_cx = min(x for x, _y in component)
        normalized_component = {(x - min_cx, y - args.baseline) for x, y in component}
        print(
            f"homonym-one-source-component8: pixels={len(component)} "
            f"page_x={min_cx}..{max(x for x, _y in component)} "
            f"page_y={min(y for _x, y in component)}..{max(y for _x, y in component)}"
        )
        print(f"  normalized: {_fmt_points(normalized_component)}")

    _compare_group(
        "current",
        current,
        raw,
        baseline=args.baseline,
        left=left,
        probe_right=probe_right,
    )
    _compare_group(
        "historical",
        historical,
        raw,
        baseline=args.baseline,
        left=left,
        probe_right=probe_right,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
