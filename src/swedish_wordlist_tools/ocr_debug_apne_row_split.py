from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_debug_left_edge_cases import _black_points
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_split_left_support import split_left_support_decision


# Page 39, column 0: the current segmentation creates a three-raster-row
# pseudo-row from the high mark over the following "apne" row.
PAGE = 39
LEFT = 2
RIGHT = 255
UPPER_TOP = 543
UPPER_BOTTOM = 546
LOWER_TOP = 547
LOWER_BOTTOM = 559


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Diagnose the page-39 apne split: a tiny high fragment far into the "
            "line must not establish a row, while real low continuation rows are "
            "protected by their own left-edge support."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    source = source_for_page(read_jsonl(args.jsonl), PAGE)
    if not source:
        raise ValueError(f"no source found for page {PAGE}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    upper_crop = page.crop((LEFT, UPPER_TOP, RIGHT, UPPER_BOTTOM))
    lower_crop = page.crop((LEFT, LOWER_TOP, RIGHT, LOWER_BOTTOM))
    upper = _black_points(upper_crop, threshold=args.threshold)
    lower = _black_points(lower_crop, threshold=args.threshold)
    decision = split_left_support_decision(upper, lower)

    print(
        f"apne-split page={PAGE} upper_y={UPPER_TOP}..{UPPER_BOTTOM} "
        f"lower_y={LOWER_TOP}..{LOWER_BOTTOM}"
    )
    print(
        f"  upper ink={decision.upper.ink_pixels} leftmost_x={decision.upper.leftmost_x} "
        f"left_band_pixels={decision.upper.left_band_pixels} "
        f"left_band_rows={decision.upper.left_band_rows}"
    )
    print(
        f"  lower ink={decision.lower.ink_pixels} leftmost_x={decision.lower.leftmost_x} "
        f"left_band_pixels={decision.lower.left_band_pixels} "
        f"left_band_rows={decision.lower.left_band_rows}"
    )
    print(
        f"  start_delta={decision.start_delta} "
        f"upper_has_own_left_support={decision.upper_has_own_left_support} "
        f"looks_like_late_upper_fragment={decision.looks_like_late_upper_fragment}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
