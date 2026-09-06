from __future__ import annotations

"""Compare sequential raw-page OCR against the frozen exact-glyph references.

The historical reference baseline is row-local while the new scanner baseline is
page-absolute, so baseline numbers are intentionally not compared directly.
Instead each solved row is compared by the ordered glyph signature
``(label, model_pixels)``.  For current glyphs we also report the absolute
vertical pixel extent, making descender/border mistakes visible immediately.

The detailed reconstruction deliberately uses the same maximal facit selection
as the active sequential matcher.  Otherwise this diagnostic can report stale
subset-first glyph choices even when row discovery itself is using newer rules.
"""

import argparse
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from . import ocr_raw_page_baseline_debug as debug
from . import ocr_sequential_raw_page_rows as scanner
from . import ocr_sequential_raw_page_rows_exactmatch as active_matcher
from . import ocr_priority_fast_path as priority
from .ocr_raw_page_baseline_row import _raw_ink


def _captured(func, *args):
    buf = StringIO()
    with redirect_stdout(buf):
        result = func(*args)
    return result, [line for line in buf.getvalue().splitlines() if line]


def _load_reference(path: Path) -> dict[tuple[int, int], dict]:
    rows: dict[tuple[int, int], dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            # Historical reference columns are zero-based; the sequential raw
            # scanner uses one-based columns.
            key = (int(item["column"]) + 1, int(item["row"]))
            rows[key] = item
    return rows


def _detailed_walk(raw, baseline, models, left, right, anchor_x, first_candidates):
    page_candidates = scanner.cached._bound_page_candidates(models)
    remaining = set(raw)
    previous_style = None
    cursor = int(anchor_x)
    matches = []

    while cursor < right:
        if not matches and first_candidates is not None:
            candidates = tuple(first_candidates)
        else:
            candidates = tuple(
                scanner.cached._iter_candidates(
                    page_candidates,
                    first_glyph=not matches,
                    previous_style=previous_style,
                    row_kind="unknown",
                    leading_homonym_seen=False,
                    baseline_established=True,
                )
            )

        chosen = active_matcher._best_subset_candidate(
            candidates,
            cursor=cursor,
            baseline=baseline,
            raw=remaining,
            left=left,
            right=right,
        )

        if chosen is not None:
            model, placed, x0 = chosen
            remaining.difference_update(placed)
            ys = [y for _x, y in placed]
            matches.append(
                {
                    "label": model.label,
                    "model_pixels": len(model.pixels),
                    "style": getattr(model, "style", None),
                    "model_id": getattr(model, "model_id", None),
                    "x0": x0,
                    "y_min": min(ys),
                    "y_max": max(ys),
                    "baseline_offset_min": min(ys) - baseline,
                    "baseline_offset_max": max(ys) - baseline,
                    "placed": placed,
                }
            )
            previous_style = priority._typographic_style(model.style)
            glyph_right = max(x for x, _y in placed) + 1
            cursor = max(cursor + 1, glyph_right)
            continue

        later_x = [x for x, _y in remaining if x > cursor]
        if not later_x:
            break
        cursor = min(later_x)

    return matches


def _homonym_match(raw, baseline, models, left, text_start_x):
    page_candidates = scanner.cached._bound_page_candidates(models)
    probe_right = min(text_start_x, left + scanner.HOMONYM_PROBE_WIDTH)
    best = None
    for model, min_x, _left_pixels in page_candidates.homonym:
        for x0 in range(left - min_x, probe_right - min_x):
            placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
            if not placed:
                continue
            xs = [x for x, _y in placed]
            if min(xs) < left or max(xs) >= text_start_x:
                continue
            if placed.issubset(raw) and (best is None or len(placed) > len(best[2])):
                best = (model, x0, placed)
    if best is None:
        return None
    model, x0, placed = best
    ys = [y for _x, y in placed]
    return {
        "label": model.label,
        "model_pixels": len(model.pixels),
        "style": getattr(model, "style", None),
        "model_id": getattr(model, "model_id", None),
        "x0": x0,
        "y_min": min(ys),
        "y_max": max(ys),
        "baseline_offset_min": min(ys) - baseline,
        "baseline_offset_max": max(ys) - baseline,
        "placed": placed,
    }


def _reconstruct_matches(context, column, row, entry, cache, models):
    left, _top, right, column_bottom = scanner._column_bounds(context, column)
    initial_border = context["raw_page_initial_border_cache"][column]
    search_from = initial_border + 1 if row == 0 else cache[row - 1].border
    search_limit = min(column_bottom, search_from + scanner._provisional_height(models))
    raw = _raw_ink(
        context, left=left, right=right, top=search_from, bottom=search_limit
    )

    page_candidates = scanner.cached._bound_page_candidates(models)
    page1 = context.get("raw_page_layout_source") == "page1-raw-pixels"
    if page1 and row == 0:
        probe_first = tuple(
            scanner._bold_candidates(page_candidates, scanner.PAGE1_EXACT_LABELS)
        )
    else:
        probe_first = scanner._continuation_candidates(page_candidates)

    first_candidates = scanner._exact_first_candidates(
        raw, entry.baseline, probe_first, entry.start_x, left, right
    )
    matches = _detailed_walk(
        raw,
        entry.baseline,
        models,
        left,
        right,
        entry.start_x,
        first_candidates,
    )
    homonym = _homonym_match(raw, entry.baseline, models, left, entry.start_x)
    if homonym is not None:
        matches.append(homonym)
        matches.sort(key=lambda item: (item["x0"], item["y_min"], item["label"]))
    return matches


def _sig_reference(row):
    return [(g["label"], int(g["model_pixels"])) for g in row.get("glyphs", [])]


def _sig_current(matches):
    return [(g["label"], int(g["model_pixels"])) for g in matches]


def _glyph_text(g):
    return (
        f"{g['label']!r}/{g['model_pixels']}px"
        f"@x={g['x0']} y={g['y_min']}..{g['y_max']}"
        f" rel={g['baseline_offset_min']}..{g['baseline_offset_max']}"
        f" id={g['model_id']!r}"
    )


def _first_difference(reference, current):
    limit = min(len(reference), len(current))
    for index in range(limit):
        if reference[index] != current[index]:
            return index
    if len(reference) != len(current):
        return limit
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare sequential raw-page glyph choices with a frozen OCR reference."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("tests/reference/saol14-ocr"),
    )
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--show-matches", action="store_true")
    args = ap.parse_args()

    reference_path = args.reference_dir / f"page-{args.page:03d}.jsonl"
    reference = _load_reference(reference_path)

    models, _ = _captured(debug.load_facit_with_typography, args.facit)
    context, _ = _captured(
        debug.page_editor.build_page_context_pixel_array,
        args.jsonl,
        args.page,
        args.threshold,
    )
    context["quiet_successful_ownership"] = True
    _unused, _ = _captured(debug.cached.bind_page_candidates, context, models)
    if args.page == 1:
        _unused, _ = _captured(
            debug._install_page1_raw_layout, context, args.jsonl, args.threshold
        )

    raw_layout = context.get("raw_page_column_layout") or {}
    if raw_layout:
        columns = sorted(int(c) for c in raw_layout)
    else:
        columns_data = context["row_map"]["columns"]
        columns = (
            list(range(1, len(columns_data) + 1))
            if isinstance(columns_data, list)
            else sorted(int(c) for c in columns_data)
        )

    compared = 0
    equal = 0
    mismatches = 0
    stop = None

    for column in columns:
        row = 0
        while (column, row) in reference:
            try:
                cache, _ = _captured(
                    debug.sequential.ensure_row_cached, context, column, row, models
                )
            except RuntimeError as exc:
                stop = (column, row, str(exc))
                print(f"STOP c{column}r{row}: {exc}")
                break

            entry = cache[row]
            current = _reconstruct_matches(
                context, column, row, entry, cache, models
            )
            ref_row = reference[(column, row)]
            ref_sig = _sig_reference(ref_row)
            cur_sig = _sig_current(current)
            compared += 1

            if ref_sig == cur_sig:
                equal += 1
                if args.show_matches:
                    print(
                        f"OK c{column}r{row:03d}: glyphs={len(cur_sig)} "
                        f"baseline={entry.baseline} border={entry.border}"
                    )
            else:
                mismatches += 1
                diff = _first_difference(ref_sig, cur_sig)
                print(
                    f"DIFF c{column}r{row:03d}: first={diff} "
                    f"ref_glyphs={len(ref_sig)} current_glyphs={len(cur_sig)} "
                    f"baseline={entry.baseline} border={entry.border}"
                )
                lo = max(0, (diff or 0) - 3)
                hi = min(max(len(ref_sig), len(cur_sig)), (diff or 0) + 5)
                for i in range(lo, hi):
                    r = ref_sig[i] if i < len(ref_sig) else None
                    c = _glyph_text(current[i]) if i < len(current) else None
                    marker = ">" if i == diff else " "
                    print(f"  {marker} {i:02d} ref={r!r} current={c}")

                if current:
                    lowest = max(current, key=lambda g: g["y_max"])
                    print(
                        f"    lowest-current={_glyph_text(lowest)} "
                        f"=> expected-own-border={lowest['y_max'] + 1}"
                    )
            row += 1

        if stop is not None:
            break

    remaining_reference = len(reference) - compared
    print(
        "reference-compare-summary: "
        f"page={args.page} compared={compared} equal={equal} "
        f"mismatches={mismatches} unvisited_reference_rows={remaining_reference}"
    )
    return 1 if mismatches or stop or remaining_reference else 0


if __name__ == "__main__":
    raise SystemExit(main())
