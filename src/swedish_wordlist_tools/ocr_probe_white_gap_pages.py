from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def parse_pages(spec: str) -> list[int]:
    """Parse page selections such as ``1,3,7-10``."""
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    return sorted(page for page in pages if page > 0)


def _page_summary(page_number: int, result: dict) -> str:
    column_rows = "/".join(str(len(column["rows"])) for column in result["columns"])
    pitches = "/".join(
        "-" if column.get("row_pitch") is None else f"{float(column['row_pitch']):.1f}"
        for column in result["columns"]
    )
    split_rows = sum(
        1
        for column in result["columns"]
        for row in column["rows"]
        if row.get("source") == "white-gap-projection-split"
    )
    return (
        f"page={page_number} rows={result['row_count']} columns={column_rows} "
        f"pitch={pitches} blocks={result['block_count']} "
        f"multi_blocks={result['multi_row_block_count']} split_rows={split_rows} "
        f"chapter_markers={result.get('chapter_marker_count', 0)}"
    )


def _warnings(result: dict) -> list[str]:
    warnings: list[str] = []
    pitches = [
        float(column["row_pitch"])
        for column in result["columns"]
        if column.get("row_pitch") is not None
    ]
    if len(pitches) != len(result["columns"]):
        warnings.append("missing-pitch")
    elif max(pitches) - min(pitches) > 2.0:
        warnings.append("pitch-spread")

    markers = [
        (int(column["column"]), marker)
        for column in result["columns"]
        for marker in column.get("chapter_markers") or []
    ]
    if any(column != 0 for column, _ in markers):
        warnings.append("marker-outside-left-column")
    if len(markers) > 1:
        warnings.append("multiple-chapter-markers")

    for column in result["columns"]:
        for row in column["rows"]:
            height = int(row["page_bottom"]) - int(row["page_top"])
            pitch = float(column.get("row_pitch") or 0.0)
            if pitch and height > 1.8 * pitch:
                warnings.append(f"tall-row-c{column['column']}@{float(row['center_y']):.1f}")
                break
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run pixel-owned white-gap row segmentation across several SAOL pages."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="Comma-separated pages/ranges, e.g. 1,2,10-15")
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    selected = parse_pages(args.pages)
    if not selected:
        raise SystemExit("no valid pages selected")

    jsonl_rows = list(read_jsonl(args.jsonl))
    processed = 0
    warning_pages = 0
    marker_pages: list[int] = []

    for page_number in selected:
        source = source_for_page(jsonl_rows, page_number)
        if not source:
            print(f"page={page_number} SKIP no-source")
            continue
        page = _load_source_image(source)
        if page is None:
            print(f"page={page_number} SKIP load-failed")
            continue

        result = segment_page_rows(page, threshold=args.threshold)
        warnings = _warnings(result)
        print(_page_summary(page_number, result))
        if warnings:
            warning_pages += 1
            print("  WARN " + ", ".join(warnings))
        if int(result.get("chapter_marker_count") or 0):
            marker_pages.append(page_number)
        processed += 1

    print(
        f"SUMMARY requested={len(selected)} processed={processed} "
        f"warning_pages={warning_pages} chapter_marker_pages={marker_pages}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
