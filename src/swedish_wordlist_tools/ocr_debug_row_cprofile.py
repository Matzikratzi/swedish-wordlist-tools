from __future__ import annotations

import argparse
import cProfile
import io
import pstats
from pathlib import Path

from .ocr_glyph_review_delete import load_facit_with_typography
from . import ocr_review_page_pixel_array_glyphs_html as review


def main() -> int:
    ap = argparse.ArgumentParser(description="cProfile one complete OCR row analysis")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = review.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)

    profiler = cProfile.Profile()
    profiler.enable()
    state = review.load_review_state_pixel_array(
        context, (args.column, args.row), models
    )
    profiler.disable()

    print(
        f"target page={args.page} column={args.column} row={args.row} "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )

    for sort_key in ("tottime", "cumtime"):
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(sort_key)
        stats.print_stats(args.limit)
        print(f"\n=== cProfile sort={sort_key} top={args.limit} ===")
        print(stream.getvalue(), end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
