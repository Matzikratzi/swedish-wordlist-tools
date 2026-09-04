from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_glyph_gap_matcher import exact_matches_by_safe_gaps
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _covered(matches) -> set[tuple[int, int]]:
    rows = list(matches or [])
    return set().union(*(set(match.pixels) for match in rows)) if rows else set()


def _point_set(points) -> set[tuple[int, int]]:
    """Normalize JSON-/UI-friendly [x, y] points into hashable integer tuples."""
    return {(int(point[0]), int(point[1])) for point in (points or [])}


def _same_shape_repeats(state: dict, candidates) -> list[dict]:
    selected = list(state.get("matches") or [])
    source = _point_set(state.get("source_ink_points"))
    residual = source - _covered(selected)
    if not residual:
        return []

    crop_left, crop_top, crop_right, crop_bottom = map(int, state["crop_box"])
    width = crop_right - crop_left
    rows = []
    candidate_keys = {
        (m.label, m.style, m.x, m.baseline, frozenset(m.pixels))
        for m in candidates
    }
    seen = set()
    for proof in selected:
        relative = frozenset((x - proof.x, y - proof.baseline) for x, y in proof.pixels)
        if not relative:
            continue
        min_x = min(x for x, _y in relative)
        max_x = max(x for x, _y in relative)
        for x0 in range(-min_x, width - max_x):
            if x0 == proof.x:
                continue
            placed = frozenset((x0 + x, proof.baseline + y) for x, y in relative)
            if not placed.issubset(residual):
                continue
            key = (proof.label, proof.style, x0, proof.baseline, placed)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "label": proof.label,
                    "style": proof.style,
                    "proved_at_x": proof.x,
                    "repeat_x": x0,
                    "baseline": proof.baseline,
                    "pixels": len(placed),
                    "candidate_generated": key in candidate_keys,
                }
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose residual ink that exactly repeats an already matched glyph on the same baseline."
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
    context["quiet_successful_ownership"] = True
    state = load_review_state_pixel_array(context, (args.column, args.row), models)

    source = _point_set(state.get("source_ink_points"))
    crop_left, crop_top, crop_right, crop_bottom = map(int, state["crop_box"])
    candidates, groups = exact_matches_by_safe_gaps(
        source,
        crop_right - crop_left,
        crop_bottom - crop_top,
        models,
    )

    print(
        f"page={args.page} c{args.column} r{args.row} "
        f"baseline={state.get('baseline')} coverage={state.get('covered_pixels')}/{state.get('source_pixels')}"
    )
    print(f"safe_groups={groups}")
    print(f"exact_candidates={len(candidates)} selected={len(state.get('matches') or [])}")
    repeats = _same_shape_repeats(state, candidates)
    if not repeats:
        print("no residual exact repeat of a selected glyph found")
        return 0
    for item in repeats:
        print(
            "repeat: "
            f"label={item['label']!r} style={item['style']} "
            f"proved_x={item['proved_at_x']} repeat_x={item['repeat_x']} "
            f"baseline={item['baseline']} pixels={item['pixels']} "
            f"candidate_generated={item['candidate_generated']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
