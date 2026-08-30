from __future__ import annotations

import argparse
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v5 as v5
from . import ocr_exact_glyph_review_queue_v10 as v10
from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import (
    GlyphModel,
    Match,
    exact_matches,
    load_facit,
    load_word_debug,
    select_best_disjoint_exact,
)


def _component_row_index(comp: set[tuple[int, int]], bands: list[dict]) -> int:
    """Assign one residual connected component to one physical text row.

    This is deliberately used only *after* all exact known glyphs have been
    extracted from the multi-row raster. A source component may initially be a
    tangle of glyphs from several rows and is therefore not a glyph boundary.
    """
    overlaps: list[int] = []
    for band in bands:
        top = int(band["top"])
        bottom = int(band["bottom"])
        overlaps.append(sum(1 for _, y in comp if top <= y < bottom))
    best_overlap = max(overlaps, default=0)
    if best_overlap:
        return max(range(len(bands)), key=lambda i: (overlaps[i], -abs(i - len(bands) // 2)))

    cy = sum(y for _, y in comp) / max(1, len(comp))
    return min(
        range(len(bands)),
        key=lambda i: abs(cy - (float(bands[i]["top"]) + float(bands[i]["bottom"])) / 2.0),
    )


def _component_nearest_row_index(comp: set[tuple[int, int]], bands: list[dict]) -> int:
    """Assign a residual component by centroid to the nearest physical row centre."""
    cy = sum(y for _, y in comp) / max(1, len(comp))
    return min(
        range(len(bands)),
        key=lambda i: (
            abs(cy - (float(bands[i]["top"]) + float(bands[i]["bottom"])) / 2.0),
            i,
        ),
    )


def _filter_target_review_residual(
    unexplained: set[tuple[int, int]], bands: list[dict], target_index: int
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Keep only residual components geometrically owned by the target row."""
    if not unexplained or not bands or not (0 <= target_index < len(bands)):
        return set(unexplained), set()

    kept: set[tuple[int, int]] = set()
    rejected: set[tuple[int, int]] = set()
    for comp in v10._components(unexplained):
        if _component_nearest_row_index(comp, bands) == target_index:
            kept.update(comp)
        else:
            rejected.update(comp)
    return kept, rejected


def _assign_components_to_rows(
    ink: set[tuple[int, int]], bands: list[dict], target_index: int
) -> tuple[set[tuple[int, int]], list[set[tuple[int, int]]]]:
    """Assign residual components whole to rows after exact tangle extraction."""
    assigned = [set() for _ in bands]
    for comp in v10._components(ink):
        assigned[_component_row_index(comp, bands)].update(comp)
    return assigned[target_index], assigned


def _partition_key(matches: list[Match]) -> tuple[int, int, int, int]:
    return (
        sum(m.model_pixels for m in matches),
        sum(m.model_pixels * m.model_pixels for m in matches),
        sum(m.sources for m in matches),
        -len(matches),
    )


def _baseline_row_index(baseline: int, bands: list[dict]) -> int:
    """Return the one physical row whose vertical centre owns this baseline."""
    return min(
        range(len(bands)),
        key=lambda i: (
            abs(
                float(baseline)
                - (float(bands[i]["top"]) + float(bands[i]["bottom"])) / 2.0
            ),
            i,
        ),
    )


def _extract_exact_rows_from_tangle(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: list[GlyphModel],
    bands: list[dict],
) -> tuple[list[list[Match]], list[Match]]:
    """Extract known glyphs from a multi-row connected raster tangle."""
    candidates = exact_matches(
        ink,
        width,
        height,
        models,
        require_whole_components=False,
    )

    per_row_by_baseline: list[dict[int, list[Match]]] = [dict() for _ in bands]
    for match in candidates:
        row_index = _baseline_row_index(match.baseline, bands)
        per_row_by_baseline[row_index].setdefault(match.baseline, []).append(match)

    proposed: list[list[Match]] = []
    for by_baseline in per_row_by_baseline:
        best: list[Match] = []
        best_key: tuple[int, int, int, int] | None = None
        for baseline in sorted(by_baseline):
            selected = select_best_disjoint_exact(by_baseline[baseline])
            key = _partition_key(selected)
            if best_key is None or key > best_key:
                best = selected
                best_key = key
        proposed.append(best)

    globally_selected = select_best_disjoint_exact(match for row in proposed for match in row)
    selected_keys = {
        (m.label, m.style, m.x, m.baseline, m.pixels)
        for m in globally_selected
    }
    per_row_selected = [
        [m for m in row if (m.label, m.style, m.x, m.baseline, m.pixels) in selected_keys]
        for row in proposed
    ]
    return per_row_selected, globally_selected


def _target_x_span(debug: dict, width: int) -> tuple[int, int]:
    bbox = debug.get("target_word_bbox_in_crop")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return 0, width
    try:
        left = max(0, int(bbox[0]))
        right = min(width, left + max(0, int(bbox[2])))
    except (TypeError, ValueError):
        return 0, width
    return (left, right) if right > left else (0, width)


def _match_intersects_x(match: Match, left: int, right: int) -> bool:
    return any(left <= x < right for x, _ in match.pixels)


def _components_intersecting_x(
    ink: set[tuple[int, int]], left: int, right: int
) -> set[tuple[int, int]]:
    """Keep whole residual components that intersect the target word's x span."""
    kept: set[tuple[int, int]] = set()
    for comp in v10._components(ink):
        if any(left <= x < right for x, _ in comp):
            kept.update(comp)
    return kept


def _analyse_one(path: Path, models: list[GlyphModel]):
    raw_ink, width, height, debug = load_word_debug(path)
    context = debug.get("five_row_context") or {}
    bands = list(context.get("bands") or [])
    target_index = int(context.get("target_index", -1))

    if not bands or not (0 <= target_index < len(bands)):
        row = v10._analyse_one(path, models)
        row["five_row_context_used"] = False
        return row

    per_row_exact, all_exact = _extract_exact_rows_from_tangle(
        set(raw_ink), width, height, models, bands
    )
    covered_all = set().union(*(m.pixels for m in all_exact)) if all_exact else set()

    residual = set(raw_ink) - covered_all
    _, residual_by_row = _assign_components_to_rows(residual, bands, target_index)

    row_ink: list[set[tuple[int, int]]] = []
    for row_index in range(len(bands)):
        exact_pixels = set().union(*(m.pixels for m in per_row_exact[row_index])) if per_row_exact[row_index] else set()
        row_ink.append(exact_pixels | residual_by_row[row_index])

    # The analysis raster is deliberately wide enough to contain complete
    # neighbouring physical rows. Review ownership stays narrow: only glyphs and
    # whole residual components intersecting the original target-word x span can
    # become target-row output. Thus full neighbour rows explain spill without
    # turning every word on the middle line into a duplicate review candidate.
    target_left, target_right = _target_x_span(debug, width)
    shown = [
        m for m in per_row_exact[target_index]
        if _match_intersects_x(m, target_left, target_right)
    ]
    target_residual = _components_intersecting_x(
        residual_by_row[target_index], target_left, target_right
    )
    exact_target_pixels = set().union(*(m.pixels for m in shown)) if shown else set()
    current = exact_target_pixels | target_residual
    covered = exact_target_pixels
    raw_unexplained = current - covered
    unexplained, filtered_neighbor_residual = _filter_target_review_residual(
        raw_unexplained, bands, target_index
    )

    baselines = {m.baseline for m in shown}
    if len(baselines) == 1:
        baseline = next(iter(baselines))
        source = "wide-row-tangle+target-word+row-bound-exact-baseline"
    else:
        baseline = _raw_baseline_guess(current, height)
        source = "wide-row-tangle+target-word+raw-density-manual-seed"

    previous = set().union(*row_ink[:target_index]) if target_index else set()
    nxt = set().union(*row_ink[target_index + 1 :]) if target_index + 1 < len(row_ink) else set()

    return {
        "expected": str(debug.get("expected_word") or debug.get("headword") or ""),
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": str(debug.get("style") or "unknown"),
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in current]),
        "raw_ink": sorted([list(p) for p in raw_ink]),
        "previous_row": sorted([list(p) for p in previous]),
        "next_row": sorted([list(p) for p in nxt]),
        "uncertain_row": [],
        "removed_noise": sorted([list(p) for p in previous | nxt | filtered_neighbor_residual]),
        "filtered_neighbor_residual": sorted([list(p) for p in filtered_neighbor_residual]),
        "row_segmentation": {
            "method": "wide-physical-row-target-word-tangle-extraction",
            "bands": bands,
            "target_index": target_index,
            "target_x_span": [target_left, target_right],
            "source_band_indices": list(context.get("source_band_indices") or []),
            "outer_support_rows": list(context.get("outer_support_rows") or []),
            "row_pixel_counts": [len(p) for p in row_ink],
            "row_exact_counts": [len(matches) for matches in per_row_exact],
            "exact_pixels_all_rows": len(covered_all),
            "residual_pixels": len(residual),
            "target_residual_pixels": len(target_residual),
            "review_residual_pixels": len(unexplained),
            "filtered_neighbor_residual_pixels": len(filtered_neighbor_residual),
        },
        "five_row_context_used": True,
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": not unexplained,
        "exact": [
            {
                "label": m.label,
                "style": m.style,
                "x": m.x,
                "baseline": m.baseline,
                "pixels": sorted([list(p) for p in m.pixels]),
            }
            for m in shown
        ],
        "unexplained": sorted([list(p) for p in unexplained]),
        "recognized": "".join(m.label for m in sorted(shown, key=lambda m: (m.x, m.label, m.style))),
        "guarded_partial_matches": [],
        "source": {
            "expected_word": debug.get("expected_word"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "source_id": debug.get("source_id") or "",
            "word_file": debug.get("word_file") or "",
        },
    }


def build_html(paths: list[Path], facit_path: Path) -> str:
    original = v5._analyse_one
    v5._analyse_one = _analyse_one
    try:
        html = build_html_v6(paths, facit_path)
    finally:
        v5._analyse_one = original

    old = "lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');"
    new = """lines.push('row_segmentation='+JSON.stringify(row.row_segmentation||{}));
 lines.push('five_row_context_used='+String(!!row.five_row_context_used));
 lines.push('previous_row_pixels='+(row.previous_row||[]).length+' next_row_pixels='+(row.next_row||[]).length);
 lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');"""
    return html.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Exact-raster OCR review using physical neighbour rows and row-bound tangle extraction.")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--facit-html", type=Path, default=Path("/tmp/glyph-facit-table.html"))
    args = ap.parse_args()
    files = _expand_inputs(args.inputs)
    if not files:
        raise SystemExit("no word-debug JSON files found")
    args.out.write_text(build_html(files, args.facit), encoding="utf-8")
    args.facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")
    print(f"debug_files={len(files)}")
    print(args.out)
    print(f"facit_html={args.facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
