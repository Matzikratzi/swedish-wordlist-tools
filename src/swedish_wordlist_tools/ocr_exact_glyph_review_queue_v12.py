from __future__ import annotations

import argparse
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v5 as v5
from . import ocr_exact_glyph_review_queue_v10 as v10
from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, load_facit, load_word_debug, select_best_baseline_partition


def _component_row_index(comp: set[tuple[int, int]], bands: list[dict]) -> int:
    """Assign one indivisible connected component to one physical text row.

    Prefer the row band containing most component pixels.  Detached marks that
    fall in the whitespace between rows are assigned by vertical centre.  The
    component itself is never split.
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


def _assign_components_to_rows(
    ink: set[tuple[int, int]], bands: list[dict], target_index: int
) -> tuple[set[tuple[int, int]], list[set[tuple[int, int]]]]:
    """Return target-row ink plus ink assigned to every context row."""
    assigned = [set() for _ in bands]
    for comp in v10._components(ink):
        assigned[_component_row_index(comp, bands)].update(comp)
    return assigned[target_index], assigned


def _analyse_one(path: Path, models: list[GlyphModel]):
    raw_ink, width, height, debug = load_word_debug(path)
    context = debug.get("five_row_context") or {}
    bands = list(context.get("bands") or [])
    target_index = int(context.get("target_index", -1))

    # Old debug files remain readable.  Five-row page preparation is the new
    # preferred path; v10 is the compatibility fallback.
    if not bands or not (0 <= target_index < len(bands)):
        row = v10._analyse_one(path, models)
        row["five_row_context_used"] = False
        return row

    current, assigned = _assign_components_to_rows(set(raw_ink), bands, target_index)
    baseline, shown = select_best_baseline_partition(current, width, height, models)
    if baseline is None:
        baseline = _raw_baseline_guess(current, height)
        source = "five-row-context+raw-density-manual-seed"
    else:
        source = "five-row-context+max-exact-raster-coverage"

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    previous = set().union(*assigned[:target_index]) if target_index else set()
    nxt = set().union(*assigned[target_index + 1 :]) if target_index + 1 < len(assigned) else set()

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
        "removed_noise": sorted([list(p) for p in previous | nxt]),
        "row_segmentation": {
            "method": "five-row-context",
            "bands": bands,
            "target_index": target_index,
            "row_pixel_counts": [len(p) for p in assigned],
        },
        "five_row_context_used": True,
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": covered == current,
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
        "unexplained": sorted([list(p) for p in current - covered]),
        "recognized": "".join(m.label for m in shown),
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
    ap = argparse.ArgumentParser(description="Exact-raster OCR review using a five-physical-row context window.")
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
