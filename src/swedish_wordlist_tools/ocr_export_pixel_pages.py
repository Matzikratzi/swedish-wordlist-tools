from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from .ocr_profile_automaton_parallel_benchmark import (
    _build_minimal_page_context,
    _minimal_column_bounds,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export thresholded SAOL page pixel images with OCR column bounds."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", type=int, nargs="+", required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output-dir", type=Path, default=Path("reports/pixel-pages"))
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for page_number in args.pages:
        context = _build_minimal_page_context(args.jsonl, page_number, args.threshold)
        gray = context["gray"]
        # Exact binary image seen by the OCR: black iff gray < threshold.
        binary = gray.point(lambda value: 0 if value < args.threshold else 255, mode="1").convert("RGB")
        draw = ImageDraw.Draw(binary)

        columns = context["row_map"].get("columns") or []
        for column in range(len(columns)):
            left, right, top, bottom = _minimal_column_bounds(context, column)
            # Thin outline outside/at the OCR crop; preserve interior pixels.
            draw.rectangle((left, top, right - 1, bottom - 1), outline=(255, 0, 0), width=1)

        output = args.output_dir / f"saol14-page-{page_number:04d}-pixels.png"
        binary.save(output)
        print(f"pixel-page: page={page_number} columns={len(columns)} output={output}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
