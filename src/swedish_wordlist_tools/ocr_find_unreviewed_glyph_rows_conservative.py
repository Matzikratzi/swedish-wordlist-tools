from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_find_unreviewed_glyph_rows as scanner
from . import ocr_review_page_pixel_array_glyphs_html as pixel_review
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_conservative_late_anchor import guarded_analyser
from .ocr_conservative_row_repair import apply_conservative_row_repairs
from .ocr_conservative_row_split import apply_conservative_row_splits


def _facit_from_argv(argv: list[str]) -> Path:
    ap=argparse.ArgumentParser(add_help=False); ap.add_argument("--facit",type=Path,required=True); args,_rest=ap.parse_known_args(argv); return args.facit


def main() -> int:
    facit_path=_facit_from_argv(sys.argv[1:]); models=load_canonical_facit_with_typography(facit_path); original_build=scanner.build_page_context_pixel_array; original_analyse=pixel_review.fast.analyse_row_exact; original_loader=scanner.load_facit_with_typography
    def report_late_anchor(record):
        print("conservative-baseline-anchor: " f"ink_left={record.ink_left} old_left={record.old_left} " f"baseline={record.old_baseline}->{record.new_baseline} " f"start={record.new_label!r}/{record.new_style}@x{record.new_left} " f"pixels={record.covered_pixels}/{record.source_pixels}",flush=True)
    def build_with_conservative_repair(jsonl,page_number,threshold=210):
        context=original_build(jsonl,page_number,threshold); records=apply_conservative_row_repairs(context,models)
        for record in records: print("conservative-row-repair: " f"page={record.page} c{record.column} r{record.upper_row}/r{record.lower_row} " f"moved={record.moved_pixels} start={record.establishing_label!r}/" f"{record.establishing_style}@x{record.establishing_x} " f"baseline={record.establishing_baseline} reason={record.reason}",flush=True)
        split_records=apply_conservative_row_splits(context,models)
        for record in split_records: print("conservative-row-split: " f"page={record.page} c{record.column} r{record.old_row} cut_y={record.cut_y} " f"baselines={record.upper_baseline}/{record.lower_baseline} " f"pixels={record.upper_pixels}+{record.lower_pixels} " f"starts={record.upper_start_label!r}/{record.lower_start_label!r} " f"reason={record.reason}",flush=True)
        return context
    scanner.build_page_context_pixel_array=build_with_conservative_repair; scanner.load_facit_with_typography=lambda _path: models; pixel_review.fast.analyse_row_exact=guarded_analyser(original_analyse,on_repair=report_late_anchor)
    try: return scanner.main()
    finally: pixel_review.fast.analyse_row_exact=original_analyse; scanner.load_facit_with_typography=original_loader; scanner.build_page_context_pixel_array=original_build


if __name__=="__main__": raise SystemExit(main())
