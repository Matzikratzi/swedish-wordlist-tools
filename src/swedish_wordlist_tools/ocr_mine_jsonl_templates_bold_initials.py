from __future__ import annotations

from . import ocr_mine_jsonl_templates as base


# This module is intentionally narrow: it is only for harvesting the first
# glyph of already matched SAOL headwords. The headword text in JSONL supplies
# the character label; Tesseract is used only to split the exact matched word
# into character boxes. A wrong OCR character label must therefore not reject
# otherwise usable geometry.
def _geometry_only_charbox_match(
    boxes: list[tuple[str, int, int, int, int]], printed: str
) -> bool:
    return len(boxes) == len(printed)


base._charbox_labels_match = _geometry_only_charbox_match


if __name__ == "__main__":
    raise SystemExit(base.main())
