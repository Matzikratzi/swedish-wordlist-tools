from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_map_words import ocr_page_row_map


def grouped_row_text(records: list[dict]) -> list[dict]:
    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for record in records:
        grouped[(int(record["column"]), int(record["row_index"]))].append(record)

    rows: list[dict] = []
    for (column, row_index), items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: (int(item["bbox"][0]), str(item.get("text") or "")))
        first = items[0]
        rows.append(
            {
                "column": column,
                "row_index": row_index,
                "page_top": int(first["row_page_top"]),
                "page_bottom": int(first["row_page_bottom"]),
                "source": str(first.get("row_source") or "unknown"),
                "text": " ".join(str(item.get("text") or "").strip() for item in items if str(item.get("text") or "").strip()),
                "words": items,
            }
        )
    return rows


def filter_rows(rows: list[dict], *, column: int | None = None, contains: str | None = None) -> list[dict]:
    selected = rows
    if column is not None:
        selected = [row for row in selected if row["column"] == column]
    if contains:
        needle = contains.casefold()
        selected = [row for row in selected if needle in str(row.get("text") or "").casefold()]
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OCR rows whose geometry is owned by the white-gap pixel segmenter."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2))
    ap.add_argument("--contains", help="Show only OCR rows containing this text, case-insensitively.")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    row_map = segment_page_rows(page, threshold=args.threshold)
    records = ocr_page_row_map(page, row_map, lang=args.lang, psm=7, pad_y=1)
    rows = filter_rows(grouped_row_text(records), column=args.column, contains=args.contains)
    if args.limit >= 0:
        rows = rows[: args.limit]

    print(
        f"page={args.page} segmented_rows={row_map['row_count']} "
        f"ocr_words={len(records)} shown_rows={len(rows)}"
    )
    for row in rows:
        print(
            f"{row['column']}:{row['row_index']:02d}\t"
            f"y={row['page_top']}..{row['page_bottom']}\t"
            f"{row['text']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
