from __future__ import annotations

"""Queue editor wired to the same shared pixel-review loader as batch scanning."""

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_review_page_pixel_array_shared import load_review_state_pixel_array


page_editor.load_review_state_pixel_array = load_review_state_pixel_array

from . import ocr_review_glyph_queue_html as queue_editor  # noqa: E402


def main() -> int:
    return queue_editor.main()


if __name__ == "__main__":
    raise SystemExit(main())
