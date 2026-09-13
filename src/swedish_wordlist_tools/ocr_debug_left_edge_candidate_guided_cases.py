from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_debug_left_edge_cases import CASES, Case, _black_points, _covered, _selected_text
from .ocr_glyph_matcher import load_facit
from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_candidate_guided import candidate_guided_exact_hits
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def run_case(
    jsonl: Path,
    facit: Path,
    case: Case,
    *,
    threshold: int,
    limit: int,
    max_row_gap: int,
) -> None:
    source = source_for_page(read_jsonl(jsonl), case.page)
    if not source:
        raise ValueError(f"no source found for page {case.page}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    crop = page.crop(case.crop)
    black = _black_points(crop, threshold=threshold)
    models = load_facit(facit)
    hits, stats = candidate_guided_exact_hits(
        black,
        models,
        max_row_gap=max_row_gap,
        max_x=case.current_anchor_x,
    )

    print(
        f"case #{case.name}: page={case.page} column={case.column} row={case.row} "
        f"crop={case.crop} ink={len(black)} current_anchor_x={case.current_anchor_x} "
        f"current={case.current_text!r} max_row_gap={max_row_gap}"
    )
    print(
        f"  guided stats scan_positions={stats.scan_positions} "
        f"started_tracks={stats.started_tracks} relation_steps={stats.relation_steps} "
        f"expected_pixel_checks={stats.expected_pixel_checks} "
        f"exact_checks={stats.exact_checks} "
        f"max_requested_bottom_y={stats.max_requested_bottom_y}"
    )
    if not hits:
        print("  guided: no exact glyph placement")
        return

    by_steps: dict[int, int] = {}
    for hit in hits:
        by_steps[hit.matched_steps] = by_steps.get(hit.matched_steps, 0) + 1
    histogram = " ".join(
        f"{steps}:{count}" for steps, count in sorted(by_steps.items(), reverse=True)
    )
    strongest = hits[0].matched_steps
    print(
        f"  guided exact-placements={len(hits)} strongest_steps={strongest} "
        f"by_steps={histogram}"
    )

    for rank, hit in enumerate(hits[:limit], 1):
        source_top = hit.translate_y + hit.model.min_y
        print(
            f"  rank={rank:>2} steps={hit.matched_steps:>2} "
            f"glyph={hit.model.label!r}/{hit.model.style} px={len(hit.model.pixels):>3} "
            f"place=({hit.translate_x},{hit.translate_y}) "
            f"glyph_top=({hit.translate_x},{source_top}) "
            f"anchor_src=({hit.source_anchor_x},{hit.source_anchor_y}) "
            f"anchor_model=({hit.model_anchor_x},{hit.model_anchor_y}) "
            f"scan_x={hit.scan_x} requested_bottom_y={hit.requested_bottom_y} "
            f"baseline_local={hit.baseline} baseline_page={case.crop[1] + hit.baseline}"
        )

    baseline_sources: dict[int, list[str]] = {}
    for hit in hits:
        if hit.matched_steps != strongest:
            break
        baseline_sources.setdefault(hit.baseline, []).append(
            f"{hit.model.label!r}/{hit.model.style}@x{hit.translate_x}:steps={hit.matched_steps}"
        )

    rows = []
    for baseline, sources in sorted(baseline_sources.items()):
        selected = _select_at_baseline(black, crop.width, crop.height, models, baseline)
        covered = _covered(selected)
        rows.append((len(covered), baseline, selected, sources))
    rows.sort(key=lambda row: (-row[0], row[1]))

    for rank, (covered_pixels, baseline, selected, sources) in enumerate(rows, 1):
        text = _selected_text(selected)
        fully_exact = bool(black) and covered_pixels == len(black)
        print(
            f"  baseline-probe rank={rank} baseline={baseline} "
            f"coverage={covered_pixels}/{len(black)} fully_exact={fully_exact} "
            f"selected={len(selected)} text={text!r} "
            f"anchors={';'.join(sources)}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Probe the collected #2 rows with a candidate-guided local left-edge "
            "walker.  After the first observed dx relation, each glyph candidate "
            "predicts the exact source contour pixels that should follow; there "
            "is no fixed fingerprint depth."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit-v2.json"),
    )
    ap.add_argument("--case", choices=[case.name for case in CASES], action="append")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--max-row-gap", type=int, default=1)
    args = ap.parse_args()

    selected = CASES if not args.case else tuple(
        case for case in CASES if case.name in args.case
    )
    for n, case in enumerate(selected):
        if n:
            print()
        run_case(
            args.jsonl,
            args.facit,
            case,
            threshold=args.threshold,
            limit=args.limit,
            max_row_gap=args.max_row_gap,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
