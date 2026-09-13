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
    return moved


def _compact_repaired_column(context: dict, column: int, suppressed: set[int]) -> None:
    """Turn suppressed pseudo-rows into real geometric merges.

    Detection is done against the untouched historical row indexes.  Once all
    conservative decisions for a column are known, compact the row map exactly
    once and remap every ownership byte in that column to the new index.  Ink
    from a suppressed upper pseudo-row has already been moved to its lower row,
    so the surviving lower row becomes the merged physical row and inherits the
    earliest page_top of the pair.
    """
    if not suppressed:
        return
    entry = context["row_map"]["columns"][column]
    old_rows = list(entry.get("rows") or [])
    owners = context["pixel_owners"]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))

    survivors: list[dict] = []
    old_to_new: dict[int, int] = {}
    for old_index, old_row in enumerate(old_rows):
        if old_index in suppressed:
            continue
        row = dict(old_row)
        if old_index - 1 in suppressed:
            upper = old_rows[old_index - 1]
            row["page_top"] = min(int(upper["page_top"]), int(row["page_top"]))
            if "upper_hard_gap" in upper:
                row["upper_hard_gap"] = upper["upper_hard_gap"]
            row["source"] = "conservative-merged-row"
            row["conservative_merged_from"] = [old_index - 1, old_index]
        new_index = len(survivors)
        row["index"] = new_index
        survivors.append(row)
        old_to_new[old_index] = new_index

    # A suppressed upper row has already been recoloured to its immediate lower
    # row.  Thus only surviving old owner codes should remain here.  Remap all
    # of them to the compacted zero-based row indexes.
    code_map = {
        owners.row_code(old_index): owners.row_code(new_index)
        for old_index, new_index in old_to_new.items()
    }
    for page_y in range(owners.height):
        start = page_y * owners.width
        for page_x in range(left, right):
            offset = start + page_x
            replacement = code_map.get(owners.data[offset])
            if replacement is not None:
                owners.data[offset] = replacement

    entry["rows"] = survivors


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
    """Merge only facit-proven tiny pseudo-rows into the real row below.

    The existing white-gap/projection segmentation remains the default.  This
    pass examines only adjacent pairs where the upper row is tiny.  The pair is
    merged only when the first strong exact glyph in the legal SAOL start zone
    establishes the lower physical row and all combined ink is vertically
    compatible with that baseline.  No other split is changed.

    A proven merge is committed atomically at the end of each column: row-map
    geometry, positions and page-wide byte ownership are compacted together.
    """
    if context.get("conservative_row_repairs_applied"):
        return list(context.get("conservative_row_repairs") or [])

    geometry = row_start_geometry(homonym_start_x, headword_start_x, continuation_start_x)
    min_relative_y = min(model.min_y for model in models)
    max_relative_y = max(model.max_y for model in models)
    suppressed_positions: set[tuple[int, int]] = set()
    records: list[ConservativeRowRepairRecord] = []

    for column, entry in enumerate(context["row_map"].get("columns") or []):
        rows = entry.get("rows") or []
        left, right = _column_span(context, column)
        if right <= left:
            continue
        pitch = int(round(float(entry.get("row_pitch") or 0.0)))
        max_row_distance = max(16, min(24, pitch + 6 if pitch else 22))
        suppressed_here: set[int] = set()

        for upper_row in range(len(rows) - 1):
            lower_row = upper_row + 1
            if upper_row in suppressed_here:
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
            suppressed_here.add(upper_row)
            suppressed_positions.add((column, upper_row))
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

        _compact_repaired_column(context, column, suppressed_here)

    if suppressed_positions:
        context["positions"] = [
            (column, row_index)
            for column, entry in enumerate(context["row_map"].get("columns") or [])
            for row_index, _row in enumerate(entry.get("rows") or [])
        ]
        context["row_map"]["row_count"] = len(context["positions"])
        context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
        context["pixel_owner_row_revisions"] = {}

    context["conservative_suppressed_positions"] = sorted(suppressed_positions)
    context["conservative_row_repairs"] = records
    context["conservative_row_repairs_applied"] = True
    return records


def repair_record_dict(record: ConservativeRowRepairRecord) -> dict:
    return asdict(record)
