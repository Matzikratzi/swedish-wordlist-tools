from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v2 as v2
from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import load_facit, load_word_debug, select_best_baseline_partition


def _analyse_one(path: Path, models):
    """Analyse one raster without using its known transcription for recognition."""
    ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    word_style = str(debug.get("style") or (debug.get("card_dataset") or {}).get("style") or "bold")

    baseline, shown = select_best_baseline_partition(ink, width, height, models)
    if baseline is None:
        # Only a seed for manual annotation when the facit cannot recognize any
        # glyph at all. It does not create or accept an OCR match.
        baseline = _raw_baseline_guess(ink, height)
        source = "raw-density-manual-seed"
    else:
        source = "max-exact-raster-coverage"

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    return {
        "expected": expected,
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": word_style,
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in ink]),
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": covered == ink,
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
        "unexplained": sorted([list(p) for p in ink - covered]),
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
    """Reuse the v2 annotation UI, but feed it generic OCR analysis rows."""
    original = v2._analyse_one
    v2._analyse_one = _analyse_one
    try:
        html = v2.build_html(paths, facit_path)
    finally:
        v2._analyse_one = original
    return html.replace(
        "Automatiska träffar söker fritt bland alla stilar men måste vara 100 % exakta och ligga i rätt ordningsföljd.",
        "Automatiska träffar använder inte facitordet: alla modeller provas fritt och den pixel-disjunkta kombination som bäst täcker rastret på en gemensam stödlinje väljs.",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster SAOL glyph OCR review.")
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
