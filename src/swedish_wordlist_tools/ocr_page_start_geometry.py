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
    headword: tuple[int, ...] = ()
    continuation: tuple[int, ...] = ()
    homonym: tuple[int, ...] = ()


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


def _coarse_classes(
    values: Iterable[int],
    *,
    max_gap: int = 2,
    max_classes: int = 3,
) -> tuple[tuple[int, ...], ...]:
    """Group row minima into at most three geometric row-start families."""
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
    """Return x on the first raster row that enters a coarse start window."""
    for y in range(top, bottom):
        x = profile.at(y)
        if x is not None and lo <= x <= hi:
            return int(x)
    return None


def _two_start_values(entries: Iterable[int]) -> tuple[int, ...]:
    """Return the two best-supported discrete raster starts for one family."""
    counts = Counter(int(x) for x in entries)
    chosen = sorted(counts, key=lambda x: (-counts[x], x))[:2]
    return tuple(sorted(chosen))


def infer_page_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer strict row-start x values for one already selected column.

    The caller supplies rows from exactly one column, so every result here is
    column-local.  Existing broad geometry is used only as a bootstrap:

    1. Per-row left minima form up to three recurring geometric families.
    2. Within each family's coarse tolerance window, scan each row downward and
       record the first raster y whose left profile enters that window.
    3. Keep the two best-supported discrete x values for each family.

    Family order is purely geometric.  With three families, left-to-right is
    homonym, headword, continuation.  With two families, left-to-right is
    headword, continuation.  No glyph, page or row special case is involved.
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

    classes = _coarse_classes(x for _row, x in row_minima)
    if not classes:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    class_entries: list[list[int]] = [[] for _ in classes]
    all_entries: list[int] = []

    for row, row_minimum in row_minima:
        class_index = _class_for_x(row_minimum, classes)
        if class_index is None:
            continue
        group = classes[class_index]
        entry_x = _first_entry_x(
            profile,
            top=int(row["page_top"]),
            bottom=int(row["page_bottom"]),
            lo=min(group) - tolerance,
            hi=max(group) + tolerance,
        )
        if entry_x is None:
            continue
        class_entries[class_index].append(entry_x)
        all_entries.append(entry_x)

    starts = tuple(_two_start_values(entries) for entries in class_entries)

    homonym: tuple[int, ...] = ()
    headword: tuple[int, ...] = ()
    continuation: tuple[int, ...] = ()
    if len(starts) >= 3:
        homonym, headword, continuation = starts[:3]
    elif len(starts) == 2:
        headword, continuation = starts
    elif len(starts) == 1:
        headword = starts[0]

    strict = tuple(sorted(set(homonym + headword + continuation)))
    return InferredStartGeometry(
        centers=strict,
        ranges=tuple((x, x) for x in strict),
        observations=tuple(all_entries),
        headword=headword,
        continuation=continuation,
        homonym=homonym,
    )
