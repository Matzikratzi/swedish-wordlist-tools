from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


def connected_ink_components(image: Image.Image, *, threshold: int = 210) -> list[dict]:
    """Return 8-connected ink components in left-to-right order.

    These are deliberately called components rather than glyphs: dots, accents,
    punctuation and touching letters mean that one printed glyph need not equal
    one connected component.
    """
    gray = image.convert("L")
    pixels = gray.load()
    ink = {(x, y) for y in range(gray.height) for x in range(gray.width) if pixels[x, y] < threshold}
    components: list[dict] = []
    while ink:
        start = min(ink, key=lambda point: (point[0], point[1]))
        ink.remove(start)
        queue = deque([start])
        points = [start]
        while queue:
            x, y = queue.popleft()
            for ny in range(max(0, y - 1), min(gray.height, y + 2)):
                for nx in range(max(0, x - 1), min(gray.width, x + 2)):
                    if (nx, ny) in ink:
                        ink.remove((nx, ny))
                        queue.append((nx, ny))
                        points.append((nx, ny))
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        components.append({
            "left": min(xs),
            "top": min(ys),
            "right": max(xs) + 1,
            "bottom": max(ys) + 1,
            "width": max(xs) - min(xs) + 1,
            "height": max(ys) - min(ys) + 1,
            "pixels": len(points),
        })
    components.sort(key=lambda item: (item["left"], item["top"], item["right"], item["bottom"]))
    return components


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect connected ink components in one pixel-owned SAOL row.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--min-pixels", type=int, default=1)
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    row_map = segment_page_rows(page, threshold=args.threshold)
    column_entry = row_map["columns"][args.column]
    rows = column_entry.get("rows") or []
    if not 0 <= args.row < len(rows):
        raise SystemExit(f"row {args.row} out of range; column {args.column} has {len(rows)} rows")
    row = rows[args.row]

    rule_x = _persistent_left_rule_x(page, column_entry, threshold=args.threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(
        row,
        column=args.column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )
    crop = page.crop(box).convert("L")
    components = [
        item
        for item in connected_ink_components(crop, threshold=args.threshold)
        if item["pixels"] >= args.min_pixels
    ]

    print(
        f"page={args.page} column={args.column} row={args.row} "
        f"y={row['page_top']}..{row['page_bottom']} "
        f"rule_x={rule_x} crop_left={box[0]} components={len(components)}"
    )
    for index, item in enumerate(components):
        page_left = box[0] + item["left"]
        page_right = box[0] + item["right"]
        page_top = box[1] + item["top"]
        page_bottom = box[1] + item["bottom"]
        print(
            f"{index:02d}\tx={page_left}..{page_right}\ty={page_top}..{page_bottom}\t"
            f"w={item['width']} h={item['height']} px={item['pixels']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
