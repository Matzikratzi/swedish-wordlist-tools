from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import (
    _estimated_rows_for_block,
    _split_positions,
    column_blocks,
    estimate_row_pitch,
    estimate_single_row_ink_height,
    rows_from_blocks,
)
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Explain the white-gap row segmentation around one physical row."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    source = source_for_page(read_jsonl(args.jsonl), args.page)
    if not source:
        raise ValueError(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    left = args.column * page.width // 3
    right = (args.column + 1) * page.width // 3 if args.column < 2 else page.width
    blocks = column_blocks(page, left=left, right=right, threshold=args.threshold)
    pitch = estimate_row_pitch(blocks)
    if pitch is None:
        raise ValueError("could not estimate row pitch")
    single_height = estimate_single_row_ink_height(blocks, pitch)
    rows = rows_from_blocks(
        page,
        blocks,
        left=left,
        right=right,
        row_pitch=pitch,
        threshold=args.threshold,
    )
    if not 0 <= args.row < len(rows):
        raise ValueError(f"row {args.row} out of range; column has {len(rows)} rows before header trimming")

    target = rows[args.row]
    target_top = int(target["page_top"])
    target_bottom = int(target["page_bottom"])
    print(
        f"target page={args.page} column={args.column} row={args.row} "
        f"top={target_top} bottom={target_bottom} height={target_bottom-target_top} "
        f"source={target.get('source')}"
    )
    print(f"pitch={pitch:.3f} single_row_ink_height={single_height}")

    relevant = []
    for index, block in enumerate(blocks):
        bbox = block.get("ink_bbox")
        if not bbox:
            continue
        _x0, top, _x1, bottom = map(int, bbox)
        if bottom < target_top - round(pitch) or top > target_bottom + round(pitch):
            continue
        estimated = _estimated_rows_for_block(
            block,
            row_pitch=pitch,
            single_row_ink_height=single_height,
        )
        splits = _split_positions(
            page,
            block,
            row_count=estimated,
            row_pitch=pitch,
            left=left,
            right=right,
            threshold=args.threshold,
        )
        relevant.append((index, block, estimated, splits))

    for index, block, estimated, splits in relevant:
        bbox = list(map(int, block.get("ink_bbox") or []))
        print(
            f"block[{index}] bbox={bbox} ink_height={block.get('ink_height')} "
            f"ink_pixels={block.get('ink_pixels')} gap_distance={float(block.get('distance') or 0):.3f} "
            f"estimated_rows={estimated} splits={splits} "
            f"upper_gap={int(block['upper_gap_top'])}..{int(block['upper_gap_bottom'])} "
            f"lower_gap={int(block['lower_gap_top'])}..{int(block['lower_gap_bottom'])}"
        )

    lo = max(0, args.row - 2)
    hi = min(len(rows), args.row + 3)
    for index in range(lo, hi):
        row = rows[index]
        print(
            f"row[{index}] top={int(row['page_top'])} bottom={int(row['page_bottom'])} "
            f"height={int(row['page_bottom'])-int(row['page_top'])} "
            f"source={row.get('source')} parent_estimated_rows={row.get('parent_estimated_rows')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
