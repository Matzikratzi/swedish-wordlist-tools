from __future__ import annotations

"""Map physical headword-start rows to known JSONL first letters conservatively.

SAOL headwords are printed in dictionary order and the facsimile JSONL carries
the visible heading in ``ord``.  We use only the first visible letter as an OCR
hint.  The mapping is enabled only when the number of physical rows starting at
the learned headword/homonym x positions exactly equals the number of primary
JSONL headings on the page.  Otherwise no letter hint is supplied.

This keeps the hint result-neutral: an uncertain page/row alignment simply
falls back to pixel-only matching.
"""

import html
import re
from pathlib import Path

from .ocr_prepare_sequential_page import _page_from_row, read_jsonl


_SUP_RE = re.compile(r"<sup>.*?</sup>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def visible_heading(raw: object) -> str:
    text = html.unescape(str(raw or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return text.strip()


def heading_initial(raw: object) -> str | None:
    for char in visible_heading(raw):
        if char.isalpha():
            return char
    return None


def _primary_page_headings(jsonl: Path, page: int) -> list[str]:
    headings: list[str] = []
    seen_source_ids: set[tuple[str, str, str]] = set()
    for row in read_jsonl(jsonl):
        if _page_from_row(row) != int(page):
            continue
        # homonr=0 is primarily an alternative/secondary heading belonging to
        # an already established printed article.  It must not consume another
        # physical headword-start row.
        if str(row.get("homonr") or "") == "0":
            continue
        heading = visible_heading(row.get("ord"))
        if not heading:
            continue
        source_key = (
            str(row.get("urspr_lopnr") or ""),
            str(row.get("subnr") or ""),
            str(row.get("homonr") or ""),
        )
        # Keep real homonyms distinct, but avoid accidental repeated raw copies.
        key = source_key if any(source_key) else (heading, str(len(headings)), "")
        if key in seen_source_ids:
            continue
        seen_source_ids.add(key)
        headings.append(heading)
    return headings


def _row_start_x(context: dict, position: tuple[int, int]) -> int | None:
    column, row_index = map(int, position)
    columns = context.get("row_map", {}).get("columns") or []
    if not 0 <= column < len(columns):
        return None
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        return None
    owners = context.get("pixel_owners")
    if owners is None:
        return None

    row = rows[row_index]
    content_left = (context.get("column_content_lefts") or {}).get(column)
    left = max(
        0,
        int(
            content_left
            if content_left is not None
            else columns[column].get("crop_left", columns[column].get("left", 0))
        ),
    )
    right = min(
        owners.width,
        int(columns[column].get("crop_right", columns[column].get("right", owners.width))),
    )
    top = max(0, int(row.get("page_top", 0)))
    bottom = min(owners.height, int(row.get("page_bottom", owners.height)))
    code = owners.row_code(row_index)
    for x in range(left, right):
        if any(owners.data[y * owners.width + x] == code for y in range(top, bottom)):
            return x
    return None


def _most_common_x(context: dict, key: str, column: int) -> int | None:
    counter = (context.get(key) or {}).get(column)
    if not counter:
        return None
    return int(counter.most_common(1)[0][0])


def _build_mapping(context: dict) -> dict[tuple[int, int], str]:
    jsonl = context.get("jsonl_path")
    page = context.get("page_number")
    if jsonl is None or page is None:
        return {}

    headings = _primary_page_headings(Path(jsonl), int(page))
    if not headings:
        return {}

    starts: list[tuple[int, int]] = []
    for position in context.get("positions") or []:
        column = int(position[0])
        start_x = _row_start_x(context, position)
        if start_x is None:
            continue
        headword_x = _most_common_x(context, "priority_headword_x_counts", column)
        homonym_x = _most_common_x(context, "priority_homonym_x_counts", column)
        if (headword_x is not None and start_x == headword_x) or (
            homonym_x is not None and start_x == homonym_x
        ):
            starts.append((int(position[0]), int(position[1])))

    context["headword_initial_hint_counts"] = {
        "jsonl_headings": len(headings),
        "physical_starts": len(starts),
    }
    if len(starts) != len(headings):
        context["headword_initial_hint_status"] = "count-mismatch"
        return {}

    mapping: dict[tuple[int, int], str] = {}
    for position, heading in zip(starts, headings):
        initial = heading_initial(heading)
        if initial is not None:
            mapping[position] = initial
    context["headword_initial_hint_status"] = "exact-count-map"
    context["headword_initial_hint_headings"] = headings
    return mapping


def expected_headword_initial(context: dict, position: tuple[int, int]) -> str | None:
    """Return a known first letter only for an exactly aligned page sequence."""
    # Learned headword x counters change as exact rows are observed, so retry a
    # previously mismatching map.  Once exact-count alignment succeeds it is
    # stable for the current page geometry.
    mapping = context.get("headword_initial_hint_map")
    if mapping is None or context.get("headword_initial_hint_status") != "exact-count-map":
        mapping = _build_mapping(context)
        if mapping:
            context["headword_initial_hint_map"] = mapping
    return (mapping or {}).get((int(position[0]), int(position[1])))
