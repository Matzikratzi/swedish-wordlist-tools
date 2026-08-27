from __future__ import annotations

import argparse
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v5 as v5
from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, Match, load_facit, load_word_debug, select_best_baseline_partition


def _components(points: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
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


def _span_x(points: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in points]
    return min(xs), max(xs)


def _overlap_x(a: set[tuple[int, int]] | frozenset[tuple[int, int]], b: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> bool:
    a0, a1 = _span_x(a)
    b0, b1 = _span_x(b)
    return max(a0, b0) <= min(a1, b1)


def _model_body_and_detached(model: GlyphModel) -> tuple[set[tuple[int, int]], list[set[tuple[int, int]]]]:
    comps = _components(model.pixels)
    body = max(comps, key=lambda c: (len(c), -min(abs(y) for _, y in c)))
    return body, [c for c in comps if c is not body]


def _learn_typographic_geometry(models: list[GlyphModel], style: str) -> tuple[int, int, int, int]:
    """Learn ordinary body extents and maximum detached-component gaps.

    The gap is measured from the nearest edge of the main body to the nearest
    edge of a detached component.  It is deliberately label-agnostic: accents,
    rings, dots, trema etc. all contribute evidence about how far detached ink
    can plausibly sit from a glyph body in this typeface/style.
    """
    rows = [m for m in models if m.style == style] or list(models)
    if not rows:
        return 0, 0, 0, 0

    body_above = 0
    body_below = 0
    max_top_gap = 0
    max_bottom_gap = 0
    for model in rows:
        body, detached = _model_body_and_detached(model)
        body_top = min(y for _, y in body)
        body_bottom = max(y for _, y in body)
        body_above = max(body_above, max(0, -body_top))
        body_below = max(body_below, max(0, body_bottom))
        for comp in detached:
            comp_top = min(y for _, y in comp)
            comp_bottom = max(y for _, y in comp)
            if comp_bottom < body_top:
                max_top_gap = max(max_top_gap, body_top - comp_bottom - 1)
            elif comp_top > body_bottom:
                max_bottom_gap = max(max_bottom_gap, comp_top - body_bottom - 1)
    return body_above, body_below, max_top_gap, max_bottom_gap


def _vertical_gap(comp: set[tuple[int, int]], body: set[tuple[int, int]], side: str) -> int:
    if side == "top":
        return min(y for _, y in body) - max(y for _, y in comp) - 1
    return min(y for _, y in comp) - max(y for _, y in body) - 1


def _trim_neighbor_noise(
    ink: set[tuple[int, int]],
    baseline: int,
    models: list[GlyphModel],
    style: str,
    seed_matches: list[Match],
    *,
    tolerance: int = 1,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]], tuple[int, int], tuple[int, int]]:
    body_above, body_below, max_top_gap, max_bottom_gap = _learn_typographic_geometry(models, style)
    y0 = baseline - body_above
    y1 = baseline + body_below
    comps = _components(ink)
    main = [c for c in comps if any(y0 <= y <= y1 for _, y in c)]
    protected_pixels = set().union(*(m.pixels for m in seed_matches)) if seed_matches else set()

    kept: set[tuple[int, int]] = set()
    removed: set[tuple[int, int]] = set()
    for comp in comps:
        if comp in main or comp & protected_pixels:
            kept.update(comp)
            continue

        if max(y for _, y in comp) < y0:
            side = "top"
            allowed_gap = max_top_gap + tolerance
        elif min(y for _, y in comp) > y1:
            side = "bottom"
            allowed_gap = max_bottom_gap + tolerance
        else:
            kept.update(comp)
            continue

        # A detached mark can only belong to this line if it is horizontally
        # associated with some main-line component and lies typographically close
        # enough to that body.  The identity of the eventual Unicode character is
        # irrelevant: this permits e.g. g-with-acute in principle, but rejects a
        # mark from the neighbouring row when the vertical gap is implausibly large.
        plausible = False
        for body in main:
            if not _overlap_x(comp, body):
                continue
            gap = _vertical_gap(comp, body, side)
            if gap >= 0 and gap <= allowed_gap:
                plausible = True
                break

        if plausible:
            kept.update(comp)
        else:
            removed.update(comp)

    return kept, removed, (body_above, body_below), (max_top_gap, max_bottom_gap)


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
        gaps = (0, 0)
    else:
        cleaned, removed, ext, gaps = _trim_neighbor_noise(raw_ink, baseline0, models, style, seed)

    baseline, shown = select_best_baseline_partition(cleaned, width, height, models)
    if baseline is None:
        baseline = baseline0
        source = "raw-density-manual-seed"
    else:
        source = "max-exact-raster-coverage"
    if removed:
        source += f"+trim-typographic-gap({len(removed)})"

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
        "detached_gap_limits": {"top": gaps[0] + 1, "bottom": gaps[1] + 1},
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
        return build_html_v6(paths, facit_path)
    finally:
        v5._analyse_one = original


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster OCR review with typographic detached-component gap trimming.")
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
