from __future__ import annotations

from dataclasses import dataclass

from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_local_index import ranked_exact_local_hits
from .ocr_row_split_left_support import row_start_geometry, row_start_is_typographically_plausible


@dataclass(frozen=True)
class ConservativeRowSplitRecord:
    page: int
    column: int
    old_row: int
    cut_y: int
    upper_baseline: int
    lower_baseline: int
    upper_pixels: int
    lower_pixels: int
    upper_start_label: str
    lower_start_label: str
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


def _owned_local_points(context: dict, column: int, row_index: int, left: int, top: int, right: int, bottom: int) -> set[tuple[int, int]]:
    owners = context["pixel_owners"]
    code = owners.row_code(row_index)
    out: set[tuple[int, int]] = set()
    for page_y in range(max(0, top), min(owners.height, bottom)):
        start = page_y * owners.width
        for page_x in range(max(0, left), min(owners.width, right)):
            if owners.data[start + page_x] == code:
                out.add((page_x - left, page_y - top))
    return out


def _baseline_candidates(black, models, *, geometry, pitch: int, min_steps: int, max_steps: int):
    hits = ranked_exact_local_hits(
        black,
        models,
        max_steps=max_steps,
        min_steps=min_steps,
        max_row_gap=1,
        max_x=geometry.late_start_limit_x,
        include_tiny_fallback=False,
    )
    by_baseline: dict[int, list] = {}
    for hit in hits:
        if hit.steps < min_steps:
            continue
        if not row_start_is_typographically_plausible(hit.translate_x, geometry):
            continue
        by_baseline.setdefault(int(hit.baseline), []).append(hit)

    candidates = []
    width = max((x for x, _y in black), default=-1) + 1
    height = max((y for _x, y in black), default=-1) + 1
    for baseline, baseline_hits in by_baseline.items():
        first = min(
            baseline_hits,
            key=lambda hit: (
                hit.translate_y + hit.model.min_y,
                hit.translate_x,
                -hit.steps,
                -len(hit.model.pixels),
            ),
        )
        selected = _select_at_baseline(black, width, height, models, baseline)
        covered = set().union(*(match.pixels for match in selected)) if selected else set()
        if not covered:
            continue
        candidates.append((baseline, first, covered))
    candidates.sort(key=lambda item: item[0])
    return candidates


def _find_exact_two_baseline_partition(black, models, *, geometry, pitch: int, min_steps: int = 7, max_steps: int = 10, pitch_tolerance: int = 3):
    candidates = _baseline_candidates(
        black,
        models,
        geometry=geometry,
        pitch=pitch,
        min_steps=min_steps,
        max_steps=max_steps,
    )
    for i, (upper_baseline, upper_hit, upper_covered) in enumerate(candidates):
        for lower_baseline, lower_hit, lower_covered in candidates[i + 1 :]:
            delta = lower_baseline - upper_baseline
            if abs(delta - pitch) > pitch_tolerance:
                continue
            if upper_covered & lower_covered:
                continue
            if upper_covered | lower_covered != black:
                continue
            upper_bottom = max(y for _x, y in upper_covered) + 1
            lower_top = min(y for _x, y in lower_covered)
            if upper_bottom > lower_top:
                continue
            return upper_baseline, upper_hit, upper_covered, lower_baseline, lower_hit, lower_covered, upper_bottom
    return None


def _commit_split(context: dict, column: int, row_index: int, cut_page_y: int) -> None:
    entry = context["row_map"]["columns"][column]
    old_rows = list(entry.get("rows") or [])
    old = old_rows[row_index]
    upper = dict(old)
    lower = dict(old)
    upper["page_bottom"] = cut_page_y
    lower["page_top"] = cut_page_y
    upper["source"] = "conservative-exact-two-baseline-split"
    lower["source"] = "conservative-exact-two-baseline-split"
    upper["conservative_split_from"] = row_index
    lower["conservative_split_from"] = row_index
    new_rows = old_rows[:row_index] + [upper, lower] + old_rows[row_index + 1 :]
    for index, row in enumerate(new_rows):
        row["index"] = index

    owners = context["pixel_owners"]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    old_codes = {index: owners.row_code(index) for index in range(len(old_rows))}
    for page_y in range(owners.height):
        start = page_y * owners.width
        for page_x in range(left, right):
            offset = start + page_x
            value = owners.data[offset]
            if value == old_codes[row_index]:
                owners.data[offset] = owners.row_code(row_index if page_y < cut_page_y else row_index + 1)
            elif value != 0 and value != 255:
                for old_index in range(row_index + 1, len(old_rows)):
                    if value == old_codes[old_index]:
                        owners.data[offset] = owners.row_code(old_index + 1)
                        break
    entry["rows"] = new_rows


def apply_conservative_row_splits(
    context: dict,
    models,
    *,
    homonym_start_x: int = 46,
    headword_start_x: int = 57,
    continuation_start_x: int = 68,
    min_steps: int = 7,
    max_steps: int = 10,
    pitch_tolerance: int = 3,
) -> list[ConservativeRowSplitRecord]:
    """Split an old row only when two exact baselines partition all its ink.

    This is deliberately stricter than ordinary OCR recognition. Two legal
    strong row-start glyphs must establish baselines about one row pitch apart;
    baseline selection at those two baselines must be disjoint and their union
    must equal every owned source pixel of the old row. Only then is geometry
    and byte ownership changed.
    """
    geometry = row_start_geometry(homonym_start_x, headword_start_x, continuation_start_x)
    records: list[ConservativeRowSplitRecord] = []

    for column, entry in enumerate(context["row_map"].get("columns") or []):
        left, right = _column_span(context, column)
        pitch = int(round(float(entry.get("row_pitch") or 0.0)))
        if pitch <= 0 or right <= left:
            continue
        row_index = 0
        while row_index < len(entry.get("rows") or []):
            rows = entry.get("rows") or []
            row = rows[row_index]
            top = int(row["page_top"])
            bottom = int(row["page_bottom"])
            # Normal single rows are much shorter than two pitches. Avoid the
            # local-index work unless geometry already permits two baselines.
            if bottom - top < pitch + 6:
                row_index += 1
                continue
            black = _owned_local_points(context, column, row_index, left, top, right, bottom)
            if not black:
                row_index += 1
                continue
            found = _find_exact_two_baseline_partition(
                black,
                models,
                geometry=geometry,
                pitch=pitch,
                min_steps=min_steps,
                max_steps=max_steps,
                pitch_tolerance=pitch_tolerance,
            )
            if found is None:
                row_index += 1
                continue
            upper_baseline, upper_hit, upper_covered, lower_baseline, lower_hit, lower_covered, cut_local_y = found
            cut_page_y = top + cut_local_y
            _commit_split(context, column, row_index, cut_page_y)
            records.append(
                ConservativeRowSplitRecord(
                    page=int(context["page_number"]),
                    column=column,
                    old_row=row_index,
                    cut_y=cut_page_y,
                    upper_baseline=top + upper_baseline,
                    lower_baseline=top + lower_baseline,
                    upper_pixels=len(upper_covered),
                    lower_pixels=len(lower_covered),
                    upper_start_label=str(upper_hit.model.label),
                    lower_start_label=str(lower_hit.model.label),
                    reason="two-exact-disjoint-baselines-cover-entire-old-row",
                )
            )
            # Skip both newly created rows; the exact partition already proved
            # that this old row contained exactly two physical rows.
            row_index += 2

    if records:
        context["positions"] = [
            (column, row_index)
            for column, entry in enumerate(context["row_map"].get("columns") or [])
            for row_index, _row in enumerate(entry.get("rows") or [])
        ]
        context["row_map"]["row_count"] = len(context["positions"])
        context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
        context["pixel_owner_row_revisions"] = {}
    context["conservative_row_splits"] = records
    return records
