from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def _compare_rows(result: dict, reference: dict, *, tolerance: float = 4.0) -> None:
    print("REFERENCE ROW COMPARISON:")
    for column in result["columns"]:
        column_index = int(column["column"])
        candidate_rows = list(column["rows"])
        reference_columns = [
            item for item in reference.get("columns") or [] if int(item.get("column", -1)) == column_index
        ]
        reference_rows = list(reference_columns[0].get("rows") or []) if reference_columns else []

        matched_candidates: set[int] = set()
        matched_references: set[int] = set()
        pairs: list[tuple[float, int, int]] = []
        for ci, candidate in enumerate(candidate_rows):
            cy = float(candidate["center_y"])
            for ri, ref in enumerate(reference_rows):
                ry = float(ref["center_y"])
                distance = abs(cy - ry)
                if distance <= tolerance:
                    pairs.append((distance, ci, ri))
        for _, ci, ri in sorted(pairs):
            if ci in matched_candidates or ri in matched_references:
                continue
            matched_candidates.add(ci)
            matched_references.add(ri)

        candidate_only = [
            row for i, row in enumerate(candidate_rows) if i not in matched_candidates
        ]
        reference_only = [
            row for i, row in enumerate(reference_rows) if i not in matched_references
        ]
        print(
            f"column={column_index} candidate={len(candidate_rows)} reference={len(reference_rows)} "
            f"matched={len(matched_candidates)} candidate_only={len(candidate_only)} "
            f"reference_only={len(reference_only)}"
        )
        for row in candidate_only:
            print(
                "  candidate-only "
                f"y={float(row['center_y']):.1f} top={row['page_top']} bottom={row['page_bottom']} "
                f"source={row.get('source')} parent_rows={row.get('parent_estimated_rows')}"
            )
        for row in reference_only:
            print(
                "  reference-only "
                f"y={float(row['center_y']):.1f} top={row['page_top']} bottom={row['page_bottom']} "
                f"source={row.get('source')} texts={row.get('texts') or []}"
            )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Segment one SAOL page into columns and physical rows from pixels only."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--reference-row-map", type=Path)
    ap.add_argument("--compare-tolerance", type=float, default=4.0)
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

    if args.reference_row_map:
        if not args.reference_row_map.is_file():
            raise SystemExit(f"reference row map not found: {args.reference_row_map}")
        reference = json.loads(args.reference_row_map.read_text(encoding="utf-8"))
        _compare_rows(result, reference, tolerance=max(0.0, args.compare_tolerance))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
