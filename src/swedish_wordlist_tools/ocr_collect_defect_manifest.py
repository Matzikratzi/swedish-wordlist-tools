from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from .ocr_compare_page_text_prefix import _format_duration
from .ocr_glyph_matcher import load_facit
from .ocr_review_batch_defects_html import parse_pages, scan_page


def write_manifest(path: Path, defects: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for defect in defects:
            handle.write(json.dumps(defect, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scan many SAOL pages and write every pixel-defective row to a JSONL manifest."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="page selection, e.g. 7-50 or 7-20,25,30-40")
    ap.add_argument("--output", type=Path, default=Path("data/generated/ocr-defects.jsonl"))
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    args = ap.parse_args()

    pages = parse_pages(args.pages)
    models = load_facit(args.facit)
    started = perf_counter()
    all_defects: list[dict] = []

    print(
        f"defect-manifest: skannar {len(pages)} sidor {pages[0]}..{pages[-1]} -> {args.output}",
        flush=True,
    )
    for page in pages:
        report = scan_page(
            args.jsonl,
            page,
            models,
            threshold=args.threshold,
            stop_after_first_defect=False,
            progress_store=None,
        )
        page_defects = []
        for defect in report["defects"]:
            record = {
                "page": int(page),
                "column": int(defect["column"]),
                "row": int(defect["row"]),
                "unknown_pixels": int(defect["unknown_pixels"]),
                "covered_pixels": int(defect["covered_pixels"]),
                "source_pixels": int(defect["source_pixels"]),
                "text": str(defect.get("text") or ""),
            }
            page_defects.append(record)
            all_defects.append(record)
            print(
                f"DEFECT page={record['page']} col={record['column']} row={record['row']} "
                f"unknown={record['unknown_pixels']} text={record['text']!r}",
                flush=True,
            )
        print(
            f"defect-manifest page={page}: rows={report['rows_total']} defects={len(page_defects)} "
            f"elapsed={_format_duration(report['elapsed'])}",
            flush=True,
        )

    write_manifest(args.output, all_defects)
    print(
        f"defect-manifest: klar; pages={len(pages)} defects={len(all_defects)} "
        f"elapsed={_format_duration(perf_counter() - started)} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
