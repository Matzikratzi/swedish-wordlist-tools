from __future__ import annotations

"""Batch scanner using the same shared pixel-review loader as the queue editor."""

from . import ocr_find_unreviewed_glyph_rows as scanner
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


scanner.build_page_context_pixel_array = build_page_context_pixel_array
scanner.load_review_state_pixel_array = load_review_state_pixel_array


def main() -> int:
    return scanner.main()


if __name__ == "__main__":
    raise SystemExit(main())
