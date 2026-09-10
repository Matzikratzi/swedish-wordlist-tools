from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile


@dataclass(frozen=True)
class InferredStartGeometry:
    centers: tuple[int, ...]
    ranges: tuple[tuple[int, int], ...]
    observations: tuple[int, ...]


def _profile_for_rows(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
) -> ColumnLeftProfile | None:
    reference = list(reference_rows)
    if isinstance(source, ColumnLeftProfile):
        return source
    if not reference:
        return None
    top = min(int(row["page_top"]) for row in reference)
    bottom = max(int(row["page_bottom"]) for row in reference)
    return build_column_left_profile(source, top=top, bottom=bottom)


def _row_leftmosts(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    min_row_pixels: int = 3,
) -> list[int]:
    reference = list(reference_rows)
    profile = _profile_for_rows(source, reference)
    if profile is None:
        return []

    starts: list[int] = []
    for row in reference:
        top = int(row["page_top"])
        bottom = int(row["page_bottom"])
        x = profile.row_leftmost(top, bottom)
        if x is None:
            continue

        # Preserve the old tiny-noise guard for mapping callers.  A prebuilt
        # page profile has already been constructed from the column bitmap, so
        # there is no need to walk every x merely to rediscover its minimum.
        if not isinstance(source, ColumnLeftProfile):
            count = sum(len(tuple(source.get(y, ()))) for y in range(top, bottom))
            if count < min_row_pixels:
                continue
        starts.append(x)
    return starts


def _coarse_classes(values: Iterable[int], *, max_gap: int = 2, max_classes: int = 3) -> tuple[tuple[int, ...], ...]:
    """Group row minima into at most three coarse typographic start classes.

    The old ±4 intervals were wide enough to merge neighbouring classes.  Here
    we use only the raw per-row minima to separate the page into compact x
    groups first.  A class may contain several nearby minima because italic
    glyphs can lean left after the true row start.
    """
    counts = Counter(int(x) for x in values)
    if not counts:
        return ()

    groups: list[list[int]] = []
    for x in sorted(counts):
        if not groups or x - groups[-1][-1] > max_gap:
            groups.append([x])
        else:
            groups[-1].append(x)

    if len(groups) > max_classes:
        groups = sorted(
            groups,
            key=lambda group: (-sum(counts[x] for x in group), min(group)),
        )[:max_classes]
        groups.sort(key=min)
    return tuple(tuple(group) for group in groups)


def _class_for_x(x: int, classes: tuple[tuple[int, ...], ...]) -> int | None:
    for index, group in enumerate(classes):
        if x in group:
            return index
    return None


def _first_entry_x(
    profile: ColumnLeftProfile,
    *,
    top: int,
    bottom: int,
    lo: int,
    hi: int,
) -> int | None:
    """Return the x of the first raster row entering a coarse start window."""
    for y in range(top, bottom):
        x = profile.at(y)
        if x is not None and lo <= x <= hi:
            return int(x)
    return None


def infer_page_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer strict page-local row-start x positions before OCR begins.

    Preparation is deliberately two-stage.

    First, the minimum left-profile x of each known physical row is used only
    to assign that row to one of up to three coarse typographic start classes.
    These correspond geometrically to the page's recurring row-start families;
    no semantic label such as headword, continuation or homonym is required.

    Second, for every row in a class we scan downward from its upper boundary
    and record the *first* profile x that enters that class's old coarse
    tolerance window.  This avoids mistaking a later left-leaning part of an
    italic glyph for the row start.

    The two most frequently observed entry x positions in each class become
    the page's strict legal starts.  They are returned as singleton ranges so
    existing OCR callers automatically trigger only on those discrete raster
    positions.  A class with only one observed position contributes one value.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    reference = list(reference_rows)
    profile = _profile_for_rows(source, reference)
    if profile is None or not reference:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    row_minima: list[tuple[dict, int]] = []
    for row in reference:
        top = int(row["page_top"])
        bottom = int(row["page_bottom"])
        x = profile.row_leftmost(top, bottom)
        if x is not None:
            row_minima.append((row, int(x)))

    classes = _coarse_classes((x for _row, x in row_minima))
    if not classes:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    class_entries: list[list[int]] = [[] for _ in classes]
    all_entries: list[int] = []

    for row, row_minimum in row_minima:
        class_index = _class_for_x(row_minimum, classes)
        if class_index is None:
            continue
        group = classes[class_index]
        lo = min(group) - tolerance
        hi = max(group) + tolerance
        entry_x = _first_entry_x(
            profile,
            top=int(row["page_top"]),
            bottom=int(row["page_bottom"]),
            lo=lo,
            hi=hi,
        )
        if entry_x is None:
            continue
        class_entries[class_index].append(entry_x)
        all_entries.append(entry_x)

    strict: list[int] = []
    for entries in class_entries:
        counts = Counter(entries)
        if not counts:
            continue
        chosen = sorted(counts, key=lambda x: (-counts[x], x))[:2]
        strict.extend(sorted(chosen))

    strict = sorted(set(strict))
    return InferredStartGeometry(
        centers=tuple(strict),
        ranges=tuple((x, x) for x in strict),
        observations=tuple(all_entries),
    )
