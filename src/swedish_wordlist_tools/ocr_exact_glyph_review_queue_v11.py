from __future__ import annotations

import argparse
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v5 as v5
from . import ocr_exact_glyph_review_queue_v10 as v10
from .ocr_exact_glyph_review_queue import _expand_inputs
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, load_facit


def _span_x(points: set[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in points]
    return min(xs), max(xs)


def _overlap_x(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> bool:
    a0, a1 = _span_x(a)
    b0, b1 = _span_x(b)
    return max(a0, b0) <= min(a1, b1)


def _analyse_one(path: Path, models: list[GlyphModel]):
    """Use v10 row segmentation, then guard partial body matches.

    A detached component that v10 classified as ``uncertain`` is close enough to
    the current text row to be a plausible part of a glyph.  Therefore an exact
    match for only the body underneath must remain provisional: if the match does
    not itself include the detached component, suppress that match and leave the
    whole body+mark group for manual learning.  A complete learned model such as
    å/ä/ö contains its detached pixels and is not suppressed.
    """
    row = v10._analyse_one(path, models)
    uncertain = set(tuple(p) for p in row.get("uncertain_row") or [])
    if not uncertain or not row.get("exact"):
        row["guarded_partial_matches"] = []
        return row

    uncertain_components = v10._components(uncertain)
    kept = []
    guarded = []
    for match in row["exact"]:
        mpix = set(tuple(p) for p in match.get("pixels") or [])
        if not mpix:
            kept.append(match)
            continue

        # A full glyph model that actually owns the detached mark is safe.
        # Otherwise, any horizontally associated uncertain component means the
        # apparent body match may be only the lower part of a previously unseen
        # accented/marked glyph.
        blocks = []
        for comp in uncertain_components:
            if comp.issubset(mpix):
                continue
            if _overlap_x(comp, mpix):
                blocks.append(comp)
        if blocks:
            guarded.append(
                {
                    "label": match.get("label"),
                    "style": match.get("style"),
                    "x": match.get("x"),
                    "blocked_by_pixels": sum(len(c) for c in blocks),
                }
            )
        else:
            kept.append(match)

    row["exact"] = kept
    row["guarded_partial_matches"] = guarded
    covered = set()
    for match in kept:
        covered.update(tuple(p) for p in match.get("pixels") or [])

    ink = set(tuple(p) for p in row.get("ink") or [])
    previous_row = set(tuple(p) for p in row.get("previous_row") or [])
    next_row = set(tuple(p) for p in row.get("next_row") or [])
    current_row_ink = ink - previous_row - next_row

    # v10 has already segmented neighboring rows.  Never reintroduce those
    # pixels when v11 recomputes unexplained ink after guarding a partial body
    # match.  Detached marks may belong above a glyph, but ink from a lower row
    # is not a downward diacritic.
    row["unexplained"] = sorted([list(p) for p in current_row_ink - covered])
    row["recognized"] = "".join(str(m.get("label") or "") for m in kept)
    row["fully_exact"] = covered == current_row_ink
    if guarded:
        row["baseline_source"] = str(row.get("baseline_source") or "") + f"+guard-detached({len(guarded)})"
    return row


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
 lines.push('guarded_partial_matches='+JSON.stringify(row.guarded_partial_matches||[]));
 lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');"""
    return html.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Exact-raster OCR review with row segmentation and detached-part guarding.")
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
