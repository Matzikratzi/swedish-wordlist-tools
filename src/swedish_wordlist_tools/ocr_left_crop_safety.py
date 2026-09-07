from __future__ import annotations

"""Shared horizontal safety margin for SAOL row OCR.

The historical pixel-array path briefly expanded the established content crop
by ten pixels before glyph analysis.  That expansion was later reverted, which
can leave legitimate left-protruding glyph pixels (notably homonym markers)
outside the analysed source pixels even though the remaining raster still
identifies the glyph correctly.

Existing row-OCR callers derive the content edge as ``rule_x + 2``.  Installing
this wrapper shifts the returned rule anchor ten pixels left, giving those
callers exactly the former ten-pixel left safety margin while leaving their
right edge untouched.
"""

from . import ocr_row_map_words as row_map_words


LEFT_CROP_SAFETY_MARGIN = 10


_original_persistent_left_rule_x = row_map_words._persistent_left_rule_x
_installed = False


def install_left_crop_safety_margin() -> None:
    global _installed
    if _installed:
        return

    original = row_map_words._persistent_left_rule_x

    def persistent_left_rule_x_with_safety(page_image, column_entry, *, threshold=210):
        rule_x = original(page_image, column_entry, threshold=threshold)
        if rule_x is None:
            return None
        column_left = max(0, int(column_entry.get("left") or 0))
        return max(column_left, int(rule_x) - LEFT_CROP_SAFETY_MARGIN)

    row_map_words._persistent_left_rule_x = persistent_left_rule_x_with_safety
    _installed = True
