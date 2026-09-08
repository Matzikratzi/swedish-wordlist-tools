from __future__ import annotations

from dataclasses import asdict, dataclass

from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_local_index import ranked_exact_local_hits
from .ocr_row_finder_one_at_a_time import first_known_row_start
from .ocr_row_split_left_support import (
    baseline_row_compatibility,
    conservative_split_repair_decision,
    row_start_geometry,
)


@dataclass(frozen=True)
class ConservativeRowRepairRecord:
    page: int
    column: int
    upper_row: int
    lower_row: int
    moved_pixels: int
    establishing_label: str
    establishing_style: str
    establishing_x: int
    establishing_baseline: int
    reason: str


def _column_span(context: dict, column: int) -> tuple[int, int]:
    owners = context["pixel_owners"]
    entry = context["row_map"]["columns"][column]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    return left, right


def _owned_local_points(
    context: dict,
    *,
    column: int,
    row_indexes: tuple[int, ...],
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> tuple[set[tuple[int, int]], dict[int, set[tuple[int, int]]]]:
    owners = context["pixel_owners"]
    codes = {row_index: owners.row_code(row_index) for row_index in row_indexes}
    by_row: dict[int, set[tuple[int, int]]] = {row_index: set() for row_index in row_indexes}
    combined: set[tuple[int, int]] = set()
    wanted = {code: row_index for row_index, code in codes.items()}
    for page_y in range(max(0, top), min(owners.height, bottom)):
        start = page_y * owners.width
        for page_x in range(max(0, left), min(owners.width, right)):
            row_index = wanted.get(owners.data[start + page_x])
            if row_index is None:
                continue
            point = (page_x - left, page_y - top)
            by_row[row_index].add(point)
            combined.add(point)
    return combined, by_row


def _move_upper_to_lower(
    context: dict,
    *,
    column: int,
    upper_row: int,
    lower_row: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> int:
    owners = context["pixel_owners"]
    upper_code = owners.row_code(upper_row)
    lower_code = owners.row_code(lower_row)
    moved = 0
    for page_y in range(max(0, top), min(owners.height, bottom)):
        start = page_y * owners.width
        for page_x in range(max(0, left), min(owners.width, right)):
            offset = start + page_x
            if owners.data[offset] == upper_code:
                owners.data[offset] = lower_code
                moved += 1
    if moved:
        context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
        revisions = context.setdefault("pixel_owner_row_revisions", {})
        for position in ((column, upper_row), (column, lower_row)):
            revisions[position] = int(revisions.get(position, 0)) + 1
    return moved


def apply_conservative_row_repairs(
    context: dict,
    models,
    *,
    homonym_start_x: int = 46,
    headword_start_x: int = 57,
    continuation_start_x: int = 68,
    max_upper_pixels: int = 24,
    min_steps: int = 3,
    max_steps: int = 10,
) -> list[ConservativeRowRepairRecord]:
    """Suppress only facit-proven tiny pseudo-rows above a real physical row.

    The existing white-gap/projection segmentation remains authoritative.  This
    pass examines only adjacent pairs where the upper row is tiny.  The upper
    row is suppressed only when the first strong exact glyph in the legal SAOL
    start zone establishes the lower physical row and *all* combined ink is
    vertically compatible with that baseline.  No other split is changed.

    Ownership bytes are moved from the false upper row to the lower row.  The
    row map itself is left intact so every historical row index remains stable;
    only ``context['positions']`` drops the proven pseudo-row.
    """
    if context.get("conservative_row_repairs_applied"):
        return list(context.get("conservative_row_repairs") or [])

    geometry = row_start_geometry(homonym_start_x, headword_start_x, continuation_start_x)
    min_relative_y = min(model.min_y for model in models)
    max_relative_y = max(model.max_y for model in models)
    suppressed: set[tuple[int, int]] = set()
    records: list[ConservativeRowRepairRecord] = []

    for column, entry in enumerate(context["row_map"].get("columns") or []):
        rows = entry.get("rows") or []
        left, right = _column_span(context, column)
        if right <= left:
            continue
        pitch = int(round(float(entry.get("row_pitch") or 0.0)))
        max_row_distance = max(16, min(24, pitch + 6 if pitch else 22))

        for upper_row in range(len(rows) - 1):
            lower_row = upper_row + 1
            if (column, upper_row) in suppressed:
                continue
            upper = rows[upper_row]
            lower = rows[lower_row]
            top = min(int(upper["page_top"]), int(lower["page_top"]))
            bottom = max(int(upper["page_bottom"]), int(lower["page_bottom"]))
            if bottom <= top:
                continue

            combined, by_row = _owned_local_points(
                context,
                column=column,
                row_indexes=(upper_row, lower_row),
                left=left,
                top=top,
                right=right,
                bottom=bottom,
            )
            upper_black = by_row[upper_row]
            if not upper_black or len(upper_black) > max_upper_pixels:
                continue
            upper_left = min(x for x, _y in upper_black)
            if upper_left <= geometry.late_start_limit_x:
                continue
            if not combined:
                continue

            hits = ranked_exact_local_hits(
                combined,
                models,
                max_steps=max_steps,
                min_steps=min_steps,
                max_row_gap=1,
                max_x=geometry.late_start_limit_x,
                include_tiny_fallback=False,
            )
            found = first_known_row_start(
                hits,
                geometry=geometry,
                previous_break_y=0,
                max_row_distance=max_row_distance,
                min_steps=min_steps,
            )
            if found is None:
                continue

            selected = _select_at_baseline(
                combined,
                right - left,
                bottom - top,
                models,
                found.baseline,
            )
            covered = set().union(*(match.pixels for match in selected)) if selected else set()
            compatibility = baseline_row_compatibility(
                combined,
                covered,
                baseline=found.baseline,
                min_relative_y=min_relative_y,
                max_relative_y=max_relative_y,
            )
            decision = conservative_split_repair_decision(
                upper_black,
                combined,
                geometry=geometry,
                establishing_start_x=found.x,
                compatibility=compatibility,
                max_upper_pixels=max_upper_pixels,
            )
            if not decision.repair:
                continue

            moved = _move_upper_to_lower(
                context,
                column=column,
                upper_row=upper_row,
                lower_row=lower_row,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
            )
            if not moved:
                continue
            suppressed.add((column, upper_row))
            records.append(
                ConservativeRowRepairRecord(
                    page=int(context["page_number"]),
                    column=column,
                    upper_row=upper_row,
                    lower_row=lower_row,
                    moved_pixels=moved,
                    establishing_label=found.label,
                    establishing_style=found.style,
                    establishing_x=found.x,
                    establishing_baseline=found.baseline,
                    reason=decision.reason,
                )
            )

    positions = context.get("positions") or []
    positions[:] = [position for position in positions if tuple(position) not in suppressed]
    context["conservative_suppressed_positions"] = sorted(suppressed)
    context["conservative_row_repairs"] = records
    context["conservative_row_repairs_applied"] = True
    return records


def repair_record_dict(record: ConservativeRowRepairRecord) -> dict:
    return asdict(record)
