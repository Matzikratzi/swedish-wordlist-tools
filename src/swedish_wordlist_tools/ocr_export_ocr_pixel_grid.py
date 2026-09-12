from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .ocr_profile_automaton_parallel_benchmark import _build_minimal_page_context


def _load_deferred_pixels(batch_jsonl: Path | None, page_number: int) -> set[tuple[int, int]]:
    if batch_jsonl is None or not batch_jsonl.exists():
        return set()

    with batch_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if int(record.get("page", -1)) != page_number:
                continue
            return {
                (int(point[0]), int(point[1]))
                for column in record.get("columns", [])
                for point in column.get("deferred_pixels", [])
            }
    return set()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Render the exact thresholded raster seen by the profile OCR, "
            "with one source pixel per grid cell."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--batch-jsonl", type=Path)
    ap.add_argument("--cell", type=int, default=8)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    context = _build_minimal_page_context(args.jsonl, args.page, args.threshold)
    gray = context["gray"]
    deferred = _load_deferred_pixels(args.batch_jsonl, args.page)

    cell = int(args.cell)
    if cell < 2:
        raise ValueError("--cell must be at least 2")

    margin_left = 72
    margin_top = 52
    margin_right = 24
    margin_bottom = 32

    out = Image.new(
        "RGB",
        (
            margin_left + gray.width * cell + margin_right,
            margin_top + gray.height * cell + margin_bottom,
        ),
        "white",
    )
    draw = ImageDraw.Draw(out)
    src = gray.load()

    # Exact OCR raster: black iff gray < threshold.
    for y in range(gray.height):
        y0 = margin_top + y * cell
        for x in range(gray.width):
            x0 = margin_left + x * cell
            fill = (0, 0, 0) if int(src[x, y]) < args.threshold else (255, 255, 255)
            if (x, y) in deferred:
                fill = (255, 0, 0)
            draw.rectangle(
                (x0, y0, x0 + cell - 1, y0 + cell - 1),
                fill=fill,
            )

    # Pixel grid. Every source pixel has a visible cell boundary.
    for x in range(gray.width + 1):
        sx = margin_left + x * cell
        if x % 50 == 0:
            colour, width = (30, 30, 30), 3
        elif x % 10 == 0:
            colour, width = (125, 125, 125), 2
        else:
            colour, width = (215, 215, 215), 1
        draw.line(
            (sx, margin_top, sx, margin_top + gray.height * cell),
            fill=colour,
            width=width,
        )

    for y in range(gray.height + 1):
        sy = margin_top + y * cell
        if y % 50 == 0:
            colour, width = (30, 30, 30), 3
        elif y % 10 == 0:
            colour, width = (125, 125, 125), 2
        else:
            colour, width = (215, 215, 215), 1
        draw.line(
            (margin_left, sy, margin_left + gray.width * cell, sy),
            fill=colour,
            width=width,
        )

    # Coordinate labels every 50 source pixels.
    for x in range(0, gray.width + 1, 50):
        sx = margin_left + x * cell
        draw.text((sx + 3, 12), str(x), fill=(0, 0, 0))

    for y in range(0, gray.height + 1, 50):
        sy = margin_top + y * cell
        draw.text((6, sy + 2), str(y), fill=(0, 0, 0))

    draw.text(
        (margin_left, 31),
        f"SAOL14 page {args.page} — OCR raster, threshold={args.threshold}, 1 cell = 1 OCR pixel",
        fill=(0, 0, 0),
    )
    if deferred:
        draw.text(
            (margin_left + 520, 31),
            f"red = deferred ({len(deferred)})",
            fill=(255, 0, 0),
        )

    output = args.output or Path(
        f"reports/page-{args.page:04d}-ocr-pixel-grid.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    out.save(output)

    print(
        f"ocr-pixel-grid: page={args.page} source={gray.width}x{gray.height} "
        f"threshold={args.threshold} deferred={len(deferred)} output={output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
