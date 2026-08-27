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


def _model_geometry(models: list[GlyphModel], style: str) -> tuple[int, int, int, int, int]:
    """Learn current-row body band plus plausible detached-mark geometry.

    Returns body_above, body_below, max_top_gap, max_bottom_gap and the largest
    detached-component pixel count observed in the style. These are typography
    measurements only; no character identities are used.
    """
    rows = [m for m in models if m.style == style] or list(models)
    if not rows:
        return 0, 0, 0, 0, 0

    body_above = body_below = 0
    top_gap = bottom_gap = 0
    max_detached_size = 0
    for model in rows:
        comps = _components(model.pixels)
        body = max(comps, key=lambda c: (len(c), -min(abs(y) for _, y in c)))
        body_top = min(y for _, y in body)
        body_bottom = max(y for _, y in body)
        body_above = max(body_above, max(0, -body_top))
        body_below = max(body_below, max(0, body_bottom))
        for comp in comps:
            if comp is body:
                continue
            max_detached_size = max(max_detached_size, len(comp))
            ctop = min(y for _, y in comp)
            cbottom = max(y for _, y in comp)
            if cbottom < body_top:
                top_gap = max(top_gap, body_top - cbottom - 1)
            elif ctop > body_bottom:
                bottom_gap = max(bottom_gap, ctop - body_bottom - 1)
    return body_above, body_below, top_gap, bottom_gap, max_detached_size


def _horizontal_overlap(a: set[tuple[int, int]] | frozenset[tuple[int, int]], b: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> bool:
    ax0, ax1 = min(x for x, _ in a), max(x for x, _ in a)
    bx0, bx1 = min(x for x, _ in b), max(x for x, _ in b)
    return max(ax0, bx0) <= min(ax1, bx1)


def _classify_rows(
    ink: set[tuple[int, int]],
    baseline: int,
    models: list[GlyphModel],
    style: str,
    seed_matches: list[Match],
    *,
    gap_tolerance: int = 1,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]], set[tuple[int, int]], set[tuple[int, int]], dict[str, int]]:
    """Split a generous crop into current/previous/next/uncertain ink.

    Components intersecting the learned body band belong to the current line.
    Detached components outside it remain uncertain only when they are small
    enough and close enough to be plausible detached marks of this typeface.

    There is one stronger generic rule: if detached ink lies in the x-range of
    an already pixel-perfect glyph match but is not part of that match, it cannot
    belong to that glyph. It is therefore assigned to the neighbouring row rather
    than kept as a hypothetical extra diacritic. This uses only raster evidence,
    never the known transcription.
    """
    above, below, top_gap, bottom_gap, max_detached = _model_geometry(models, style)
    y0 = baseline - above
    y1 = baseline + below
    comps = _components(ink)
    main = [c for c in comps if any(y0 <= y <= y1 for _, y in c)]
    protected_pixels = set().union(*(m.pixels for m in seed_matches)) if seed_matches else set()

    current: set[tuple[int, int]] = set()
    previous: set[tuple[int, int]] = set()
    nxt: set[tuple[int, int]] = set()
    uncertain: set[tuple[int, int]] = set()

    for comp in comps:
        if comp in main or comp & protected_pixels:
            current.update(comp)
            continue

        ctop = min(y for _, y in comp)
        cbottom = max(y for _, y in comp)
        if cbottom < y0:
            side = "top"
            allowed_gap = top_gap + gap_tolerance
            nearest = y0 - cbottom - 1
        elif ctop > y1:
            side = "bottom"
            allowed_gap = bottom_gap + gap_tolerance
            nearest = ctop - y1 - 1
        else:
            current.update(comp)
            continue

        # A perfect matched glyph is complete by definition. Extra detached ink
        # in its horizontal span is evidence from the neighbouring line, not an
        # additional part of the current glyph.
        over_known = any(_horizontal_overlap(comp, m.pixels) for m in seed_matches)
        if over_known:
            if side == "top":
                previous.update(comp)
            else:
                nxt.update(comp)
            continue

        aligned = any(_horizontal_overlap(comp, body) for body in main)
        plausible_detached = (
            aligned
            and len(comp) <= max(1, max_detached)
            and nearest <= allowed_gap
        )
        if plausible_detached:
            uncertain.update(comp)
        elif side == "top":
            previous.update(comp)
        else:
            nxt.update(comp)

    meta = {
        "body_above": above,
        "body_below": below,
        "top_gap": top_gap + gap_tolerance,
        "bottom_gap": bottom_gap + gap_tolerance,
        "max_detached_pixels": max_detached,
    }
    return current, previous, nxt, uncertain, meta


def _analyse_one(path: Path, models: list[GlyphModel]):
    raw_ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    style = str(debug.get("style") or (debug.get("card_dataset") or {}).get("style") or "bold")

    baseline0, seed = select_best_baseline_partition(raw_ink, width, height, models)
    if baseline0 is None:
        baseline0 = _raw_baseline_guess(raw_ink, height)
        seed = []

    if baseline0 is None:
        current = set(raw_ink)
        previous: set[tuple[int, int]] = set()
        nxt: set[tuple[int, int]] = set()
        uncertain: set[tuple[int, int]] = set()
        row_meta = {"body_above": 0, "body_below": 0, "top_gap": 0, "bottom_gap": 0, "max_detached_pixels": 0}
    else:
        current, previous, nxt, uncertain, row_meta = _classify_rows(raw_ink, baseline0, models, style, seed)

    ocr_ink = current | uncertain
    baseline, shown = select_best_baseline_partition(ocr_ink, width, height, models)
    if baseline is None:
        baseline = baseline0
        source = "raw-density-manual-seed"
    else:
        source = "max-exact-raster-coverage"
    if previous or nxt:
        source += f"+row-seg(prev={len(previous)},next={len(nxt)},uncertain={len(uncertain)})"

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    return {
        "expected": expected,
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": style,
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in ocr_ink]),
        "raw_ink": sorted([list(p) for p in raw_ink]),
        "previous_row": sorted([list(p) for p in previous]),
        "next_row": sorted([list(p) for p in nxt]),
        "uncertain_row": sorted([list(p) for p in uncertain]),
        "removed_noise": sorted([list(p) for p in previous | nxt]),
        "row_segmentation": row_meta,
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": covered == ocr_ink,
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
        "unexplained": sorted([list(p) for p in ocr_ink - covered]),
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

    old = "lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');"
    new = """lines.push('row_segmentation='+JSON.stringify(row.row_segmentation||{}));
 lines.push('previous_row_pixels='+(row.previous_row||[]).length+' next_row_pixels='+(row.next_row||[]).length+' uncertain_pixels='+(row.uncertain_row||[]).length);
 lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');"""
    return html.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster OCR review with explicit neighboring-row segmentation.")
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
