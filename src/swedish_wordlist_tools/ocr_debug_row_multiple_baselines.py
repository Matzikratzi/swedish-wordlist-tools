from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_conservative_row_repair import apply_conservative_row_repairs, _column_span
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_local_index import ranked_exact_local_hits
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry, row_start_is_typographically_plausible


def _owned_row_points(context: dict, column: int, row_index: int) -> tuple[set[tuple[int, int]], int, int, int, int]:
    owners = context["pixel_owners"]
    entry = context["row_map"]["columns"][column]
    rows = entry.get("rows") or []
    row = rows[row_index]
    left, right = _column_span(context, column)
    top = int(row["page_top"])
    bottom = int(row["page_bottom"])
    code = owners.row_code(row_index)
    black: set[tuple[int, int]] = set()
    for page_y in range(max(0, top), min(owners.height, bottom)):
        start = page_y * owners.width
        for page_x in range(max(0, left), min(owners.width, right)):
            if owners.data[start + page_x] == code:
                black.add((page_x - left, page_y - top))
    return black, left, top, right, bottom


def _covered(selected) -> set[tuple[int, int]]:
    return set().union(*(match.pixels for match in selected)) if selected else set()


def main() -> int:
    ap = argparse.ArgumentParser(description="Show strong legal row-start hits and baseline coverage inside one old physical row.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-start", type=int, default=46)
    ap.add_argument("--headword-start", type=int, default=57)
    ap.add_argument("--continuation-start", type=int, default=68)
    ap.add_argument("--min-steps", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=10)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    apply_conservative_row_repairs(context, models)

    rows = context["row_map"]["columns"][args.column].get("rows") or []
    if not 0 <= args.row < len(rows):
        raise ValueError(f"row {args.row} out of range after conservative repairs; column has {len(rows)} rows")

    black, left, top, right, bottom = _owned_row_points(context, args.column, args.row)
    geometry = row_start_geometry(args.homonym_start, args.headword_start, args.continuation_start)
    hits = ranked_exact_local_hits(
        black,
        models,
        max_steps=args.max_steps,
        min_steps=args.min_steps,
        max_row_gap=1,
        max_x=geometry.late_start_limit_x,
        include_tiny_fallback=False,
    )
    legal = []
    for hit in hits:
        x = int(hit.translate_x)
        if not row_start_is_typographically_plausible(x, geometry):
            continue
        top_y = int(hit.translate_y + hit.model.min_y)
        legal.append((top_y, x, -int(hit.steps), hit))
    legal.sort(key=lambda item: (item[0], item[1], item[2]))

    by_baseline: dict[int, list] = {}
    for _top_y, _x, _neg_steps, hit in legal:
        by_baseline.setdefault(int(hit.baseline), []).append(hit)

    print(
        f"row-multiple-baselines page={args.page} column={args.column} row={args.row} "
        f"box=({left},{top},{right},{bottom}) ink={len(black)} legal_hits={len(legal)} baselines={len(by_baseline)}"
    )
    for baseline in sorted(by_baseline):
        baseline_hits = by_baseline[baseline]
        first = min(
            baseline_hits,
            key=lambda hit: (
                hit.translate_y + hit.model.min_y,
                hit.translate_x,
                -hit.steps,
            ),
        )
        selected = _select_at_baseline(black, right - left, bottom - top, models, baseline)
        covered = _covered(selected)
        ys = [y for _x, y in covered]
        text = "".join(match.label for match in sorted(selected, key=lambda match: (match.x, match.baseline)))
        print(
            f"  baseline={baseline} first={first.model.label!r}/{first.model.style} "
            f"x={first.translate_x} top_y={first.translate_y + first.model.min_y} steps={first.steps} "
            f"hits={len(baseline_hits)} coverage={len(covered)}/{len(black)} "
            f"covered_y={min(ys) if ys else None}..{max(ys) if ys else None} text={text!r}"
        )

    print("  legal-start-hits:")
    for top_y, x, neg_steps, hit in legal[:40]:
        print(
            f"    top_y={top_y} baseline={hit.baseline} x={x} steps={-neg_steps} "
            f"glyph={hit.model.label!r}/{hit.model.style} pixels={len(hit.model.pixels)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
