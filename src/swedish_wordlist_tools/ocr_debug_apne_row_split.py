from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_debug_left_edge_cases import _black_points, _covered, _selected_text
from .ocr_glyph_matcher import load_facit
from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_local_index import ranked_exact_local_hits
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_finder_one_at_a_time import first_known_row_start
from .ocr_row_split_left_support import (
    baseline_row_compatibility,
    conservative_split_repair_decision,
    row_start_geometry,
    split_left_support_decision,
)


PAGE = 39
LEFT = 2
RIGHT = 255
UPPER_TOP = 543
UPPER_BOTTOM = 546
LOWER_TOP = 547
LOWER_BOTTOM = 559


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Diagnose page-39 apne both conservatively and as a one-row-at-a-time "
            "next-row finder."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit-v2.json"),
    )
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-start", type=int, default=46)
    ap.add_argument("--headword-start", type=int, default=57)
    ap.add_argument("--continuation-start", type=int, default=68)
    ap.add_argument("--max-row-distance", type=int, default=16)
    ap.add_argument("--min-steps", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=10)
    args = ap.parse_args()

    source = source_for_page(read_jsonl(args.jsonl), PAGE)
    if not source:
        raise ValueError(f"no source found for page {PAGE}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    upper_crop = page.crop((LEFT, UPPER_TOP, RIGHT, UPPER_BOTTOM))
    lower_crop = page.crop((LEFT, LOWER_TOP, RIGHT, LOWER_BOTTOM))
    combined_crop = page.crop((LEFT, UPPER_TOP, RIGHT, LOWER_BOTTOM))
    upper = _black_points(upper_crop, threshold=args.threshold)
    lower = _black_points(lower_crop, threshold=args.threshold)
    combined = _black_points(combined_crop, threshold=args.threshold)
    decision = split_left_support_decision(upper, lower)
    geometry = row_start_geometry(
        args.homonym_start,
        args.headword_start,
        args.continuation_start,
    )

    print(
        f"apne-split page={PAGE} upper_y={UPPER_TOP}..{UPPER_BOTTOM} "
        f"lower_y={LOWER_TOP}..{LOWER_BOTTOM}"
    )
    print(
        f"  upper ink={decision.upper.ink_pixels} leftmost_x={decision.upper.leftmost_x} "
        f"left_band_pixels={decision.upper.left_band_pixels} "
        f"left_band_rows={decision.upper.left_band_rows}"
    )
    print(
        f"  lower ink={decision.lower.ink_pixels} leftmost_x={decision.lower.leftmost_x} "
        f"left_band_pixels={decision.lower.left_band_pixels} "
        f"left_band_rows={decision.lower.left_band_rows}"
    )
    print(
        f"  old-evidence start_delta={decision.start_delta} "
        f"upper_has_own_left_support={decision.upper_has_own_left_support} "
        f"looks_like_late_upper_fragment={decision.looks_like_late_upper_fragment}"
    )
    print(
        "  start-geometry "
        f"homonym={geometry.homonym_start_x} headword={geometry.headword_start_x} "
        f"continuation={geometry.continuation_start_x} "
        f"late_limit={geometry.late_start_limit_x}"
    )

    models = load_facit(args.facit)
    hits = ranked_exact_local_hits(
        combined,
        models,
        max_steps=args.max_steps,
        min_steps=args.min_steps,
        max_row_gap=1,
        max_x=geometry.late_start_limit_x,
        include_tiny_fallback=False,
    )
    print(f"  indexed exact-hits={len(hits)}")

    found = first_known_row_start(
        hits,
        geometry=geometry,
        previous_break_y=0,
        max_row_distance=args.max_row_distance,
        min_steps=args.min_steps,
    )
    if found is None:
        print("  one-row-next: no known strong glyph in legal start zone")
        return 0

    print(
        f"  one-row-next glyph={found.label!r}/{found.style} steps={found.steps} "
        f"x={found.x} top_y={found.top_y} baseline={found.baseline}"
    )

    selected = _select_at_baseline(
        combined,
        combined_crop.width,
        combined_crop.height,
        models,
        found.baseline,
    )
    covered = _covered(selected)
    min_relative_y = min(model.min_y for model in models)
    max_relative_y = max(model.max_y for model in models)
    compatibility = baseline_row_compatibility(
        combined,
        covered,
        baseline=found.baseline,
        min_relative_y=min_relative_y,
        max_relative_y=max_relative_y,
    )
    print(
        f"  whole-row-baseline-probe coverage={len(covered)}/{len(combined)} "
        f"fully_exact={len(covered) == len(combined)} text={_selected_text(selected)!r}"
    )
    print(
        f"  baseline-compatible={compatibility.compatible} "
        f"unexplained={compatibility.unexplained_pixels} "
        f"outside_baseline_band={compatibility.outside_baseline_band} "
        f"font_relative_y={min_relative_y}..{max_relative_y}"
    )

    repair = conservative_split_repair_decision(
        upper,
        combined,
        geometry=geometry,
        establishing_start_x=found.x,
        compatibility=compatibility,
    )
    print(f"  conservative-repair={repair.repair} reason={repair.reason}")

    unexplained = combined - covered
    if unexplained:
        xs = [x for x, _y in unexplained]
        ys = [y for _x, y in unexplained]
        print(
            f"  unexplained pixels={len(unexplained)} "
            f"bbox=({min(xs)},{min(ys)})..({max(xs)},{max(ys)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
