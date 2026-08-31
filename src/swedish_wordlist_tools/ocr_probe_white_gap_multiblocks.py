from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import (
    _estimated_rows_for_block,
    _split_positions,
    _tight_ink_bbox,
    column_blocks,
    estimate_row_pitch,
    estimate_single_row_ink_height,
)
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def _ink_pixels_in_box(page, box, *, threshold: int) -> int:
    left, top, right, bottom = map(int, box)
    gray = page.convert("L")
    pixels = gray.load()
    return sum(
        1
        for y in range(max(0, top), min(gray.height, bottom))
        for x in range(max(0, left), min(gray.width, right))
        if pixels[x, y] < threshold
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Show detailed geometry for white-gap blocks that appear to contain multiple rows."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    for column in range(3):
        left = column * page.width // 3
        right = (column + 1) * page.width // 3 if column < 2 else page.width
        blocks = column_blocks(page, left=left, right=right, threshold=args.threshold)
        pitch = estimate_row_pitch(blocks)
        if pitch is None:
            print(f"column={column} pitch=None")
            continue
        single_ink = estimate_single_row_ink_height(blocks, pitch)
        print(
            f"column={column} x={left}..{right} pitch={pitch:.1f} "
            f"single_ink_height={single_ink}"
        )
        for block_index, block in enumerate(blocks):
            estimated = _estimated_rows_for_block(
                block,
                row_pitch=pitch,
                single_row_ink_height=single_ink,
            )
            if estimated <= 1:
                continue
            splits = _split_positions(
                page,
                block,
                row_count=estimated,
                row_pitch=pitch,
                left=left,
                right=right,
                threshold=args.threshold,
            )
            boundaries = [int(block["upper_gap_bottom"]), *splits, int(block["lower_gap_top"])]
            print(
                f"  block={block_index} estimated={estimated} "
                f"gap={float(block['upper_gap_center_y']):.1f}..{float(block['lower_gap_center_y']):.1f} "
                f"distance={float(block['distance']):.1f} "
                f"ink_bbox={block.get('ink_bbox')} ink_height={block.get('ink_height')} "
                f"ink_pixels={block.get('ink_pixels')} splits={splits}"
            )
            for slice_index, (top, bottom) in enumerate(zip(boundaries, boundaries[1:])):
                bbox = _tight_ink_bbox(
                    page,
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    threshold=args.threshold,
                )
                if bbox is None:
                    print(f"    slice={slice_index} y={top}..{bottom} empty")
                    continue
                pixels = _ink_pixels_in_box(page, bbox, threshold=args.threshold)
                height = int(bbox[3]) - int(bbox[1])
                width = int(bbox[2]) - int(bbox[0])
                print(
                    f"    slice={slice_index} y={top}..{bottom} "
                    f"ink_bbox={bbox} size={width}x{height} ink_pixels={pixels}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
