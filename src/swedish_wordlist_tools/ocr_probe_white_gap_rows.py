from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Segment one SAOL page into columns and physical rows from pixels only."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    rows = list(read_jsonl(args.jsonl))
    source = source_for_page(rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    result = segment_page_rows(page, threshold=args.threshold)
    result["page"] = args.page
    result["source"] = source

    print(
        f"page={args.page} size={page.width}x{page.height} "
        f"blocks={result['block_count']} rows={result['row_count']} "
        f"multi_blocks={result['multi_row_block_count']}"
    )
    for column in result["columns"]:
        split_rows = sum(
            1 for row in column["rows"] if row.get("source") == "white-gap-projection-split"
        )
        print(
            f"column={column['column']} x={column['left']}..{column['right']} "
            f"pitch={column['row_pitch']} blocks={column['block_count']} "
            f"multi_blocks={column['multi_row_block_count']} rows={len(column['rows'])} "
            f"split_rows={split_rows}"
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
