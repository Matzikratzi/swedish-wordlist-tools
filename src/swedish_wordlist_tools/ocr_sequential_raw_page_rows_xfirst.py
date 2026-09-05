from __future__ import annotations

"""Experimental x-first row-start discovery for the raw-page scanner.

The previous row contributes exactly one upper search boundary: ``border``.
Starting there, inspect every y in a short vertical band for each x, moving x
left-to-right.  This makes the selected x the leftmost ink column in the start
band, independent of which pixel happens to be highest.

This module deliberately reuses the existing glyph/baseline machinery while we
validate the new geometric start rule in the raw-page debug command.
"""

from . import ocr_sequential_raw_page_rows as _scanner


START_SEARCH_HEIGHT = 15


def _border_as_next_hint(
    context: dict,
    *,
    column_top: int,
    column_bottom: int,
    left: int,
    previous,
) -> int:
    """There is no separately discovered row top: start exactly at the border."""
    del context, column_bottom, left
    return column_top if previous is None else previous.border


def _x_first_text_ink_x(
    raw: set[tuple[int, int]],
    *,
    search_from: int,
    hint_y: int,
    search_limit: int,
    left: int,
    right: int,
) -> int | None:
    """Return the leftmost ordinary-text x having ink in border..border+15.

    Keep the existing homonym strip separate for now; this change isolates the
    x-first / border-relative vertical search from the later three-start-class
    refactor.
    """
    del hint_y
    x0 = min(right, left + _scanner.HOMONYM_PROBE_WIDTH)
    x1 = min(right, left + _scanner.FIRST_TEXT_SEARCH_WIDTH)
    y1 = min(search_limit, search_from + START_SEARCH_HEIGHT)
    for x in range(x0, x1):
        for y in range(search_from, y1):
            if (x, y) in raw:
                return x
    return None


# Install only the two geometric rules.  All matching, baseline verification,
# full-row walking and border calculation remain the scanner's current code.
_scanner._find_next_row_hint = _border_as_next_hint
_scanner._first_text_ink_x = _x_first_text_ink_x

CachedRowBoundary = _scanner.CachedRowBoundary
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
