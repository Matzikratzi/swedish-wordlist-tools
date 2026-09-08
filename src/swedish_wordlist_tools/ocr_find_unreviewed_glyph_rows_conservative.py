from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_find_unreviewed_glyph_rows as scanner
from .ocr_conservative_row_repair import apply_conservative_row_repairs
from .ocr_glyph_review_delete import load_facit_with_typography


def _facit_from_argv(argv: list[str]) -> Path:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--facit", type=Path, required=True)
    args, _rest = ap.parse_known_args(argv)
    return args.facit


def main() -> int:
    models = load_facit_with_typography(_facit_from_argv(sys.argv[1:]))
    original_build = scanner.build_page_context_pixel_array

    def build_with_conservative_repair(jsonl, page_number, threshold=210):
        context = original_build(jsonl, page_number, threshold)
        records = apply_conservative_row_repairs(context, models)
        for record in records:
            print(
                "conservative-row-repair: "
                f"page={record.page} c{record.column} r{record.upper_row}/r{record.lower_row} "
                f"moved={record.moved_pixels} start={record.establishing_label!r}/"
                f"{record.establishing_style}@x{record.establishing_x} "
                f"baseline={record.establishing_baseline} reason={record.reason}",
                flush=True,
            )
        return context

    scanner.build_page_context_pixel_array = build_with_conservative_repair
    try:
        return scanner.main()
    finally:
        scanner.build_page_context_pixel_array = original_build


if __name__ == "__main__":
    raise SystemExit(main())
