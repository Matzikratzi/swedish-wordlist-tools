from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from . import ocr_exact_glyph_review_queue_v5 as v5
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, load_facit, load_word_debug, select_best_baseline_partition

ACCENTED_TOP = set("åäöÅÄÖ")
DESCENDER_LABELS = set("gjpqyQ")


def _components(ink: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(ink)
    out: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            x, y = stack.pop()
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p in remaining:
                    remaining.remove(p)
                    comp.add(p)
                    stack.append(p)
        out.append(comp)
    return out


def _style_normal_extents(models: list[GlyphModel], style: str) -> tuple[int, int]:
    rows = [m for m in models if m.style == style]
    if not rows:
        rows = list(models)
    if not rows:
        return (0, 0)

    ordinary_top = [m for m in rows if not any(ch in ACCENTED_TOP for ch in m.label)] or rows
    ordinary_bottom = [m for m in rows if not any(ch in DESCENDER_LABELS for ch in m.label)] or rows
    above = max(max(0, -m.min_y) for m in ordinary_top)
    below = max(max(0, m.max_y) for m in ordinary_bottom)
    return above, below


def _x_span(comp: set[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in comp]
    return min(xs), max(xs)


def _overlap_x(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> bool:
    a0, a1 = _x_span(a)
    b0, b1 = _x_span(b)
    return max(a0, b0) <= min(a1, b1)


def _trim_neighbor_noise(
    ink: set[tuple[int, int]],
    baseline: int,
    models: list[GlyphModel],
    style: str,
    protected_pixels: set[tuple[int, int]],
) -> tuple[set[tuple[int, int]], set[tuple[int, int]], tuple[int, int]]:
    """Remove only detached components that are clearly outside the normal line band.

    The broad source crop is intentionally kept.  We infer a normal vertical band
    for the source style from learned glyphs, excluding accented ÅÄÖ/åäö from the
    upper bound and ordinary descenders from the lower bound.  A component is kept
    when it intersects that normal band, belongs to an already exact glyph match,
    or overlaps horizontally with a main-band component (so detached i-dots,
    rings/dots over unknown å/ä/ö, etc. survive).  Only detached, unprotected
    components wholly outside the band are removed as likely neighboring-line ink.
    """
    above, below = _style_normal_extents(models, style)
    y0 = baseline - above
    y1 = baseline + below
    comps = _components(ink)
    main = [c for c in comps if any(y0 <= y <= y1 for _, y in c)]

    kept: set[tuple[int, int]] = set()
    removed: set[tuple[int, int]] = set()
    for comp in comps:
        intersects_band = comp in main
        protected = bool(comp & protected_pixels)
        aligned = any(_overlap_x(comp, m) for m in main) if not intersects_band else True
        if intersects_band or protected or aligned:
            kept.update(comp)
        else:
            removed.update(comp)
    return kept, removed, (above, below)


def _analyse_one(path: Path, models: list[GlyphModel]):
    raw_ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    style = str(debug.get("style") or (debug.get("card_dataset") or {}).get("style") or "bold")

    baseline0, seed = select_best_baseline_partition(raw_ink, width, height, models)
    if baseline0 is None:
        baseline0 = _raw_baseline_guess(raw_ink, height)
    if baseline0 is None:
        cleaned = set(raw_ink)
        removed: set[tuple[int, int]] = set()
        ext = (0, 0)
    else:
        protected = set().union(*(m.pixels for m in seed)) if seed else set()
        cleaned, removed, ext = _trim_neighbor_noise(raw_ink, baseline0, models, style, protected)

    baseline, shown = select_best_baseline_partition(cleaned, width, height, models)
    if baseline is None:
        baseline = baseline0
        source = "raw-density-manual-seed"
    else:
        source = "max-exact-raster-coverage"
    if removed:
        source += f"+trim-neighbor-noise({len(removed)})"

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    return {
        "expected": expected,
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": style,
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in cleaned]),
        "raw_ink": sorted([list(p) for p in raw_ink]),
        "removed_noise": sorted([list(p) for p in removed]),
        "normal_extents": {"above": ext[0], "below": ext[1]},
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": covered == cleaned,
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
        "unexplained": sorted([list(p) for p in cleaned - covered]),
        "recognized": "".join(m.label for m in shown),
        "source": {
            "expected_word": debug.get("expected_word"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "source_id": (debug.get("card_dataset") or {}).get("sourceId") or debug.get("source_id") or "",
            "word_file": (debug.get("card_dataset") or {}).get("wordFile") or debug.get("word_file") or "",
        },
    }


def build_html(paths: list[Path], facit_path: Path) -> str:
    original = v5._analyse_one
    v5._analyse_one = _analyse_one
    try:
        html = build_html_v6(paths, facit_path)
    finally:
        v5._analyse_one = original
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster OCR review with conservative neighboring-line noise trimming.")
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
