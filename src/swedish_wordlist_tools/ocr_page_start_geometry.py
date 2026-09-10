from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile


class StartValues(tuple):
    """Tuple-compatible strict starts with useful named diagnostics."""

    def __new__(
        cls,
        values: Iterable[int],
        *,
        headword: tuple[int, ...],
        continuation: tuple[int, ...],
        homonym: tuple[int, ...],
        headword_support: tuple[int, ...] = (),
        continuation_support: tuple[int, ...] = (),
        homonym_support: tuple[int, ...] = (),
        headword_histogram: tuple[tuple[int, int], ...] = (),
        continuation_histogram: tuple[tuple[int, int], ...] = (),
        homonym_histogram: tuple[tuple[int, int], ...] = (),
    ) -> "StartValues":
        obj = super().__new__(cls, values)
        obj.headword = headword
        obj.continuation = continuation
        obj.homonym = homonym
        obj.headword_support = headword_support
        obj.continuation_support = continuation_support
        obj.homonym_support = homonym_support
        obj.headword_histogram = headword_histogram
        obj.continuation_histogram = continuation_histogram
        obj.homonym_histogram = homonym_histogram
        return obj

    @staticmethod
    def _format_pair(values: tuple[int, ...], support: tuple[int, ...]) -> str:
        if not values:
            return "()"
        if len(values) == len(support):
            details = ",".join(f"{x}:{n}" for x, n in zip(values, support))
            return f"{values}[{details}]"
        return repr(values)

    @staticmethod
    def _format_histogram(histogram: tuple[tuple[int, int], ...]) -> str:
        return "{" + ",".join(f"{x}:{n}" for x, n in histogram) + "}"

    def __repr__(self) -> str:
        return (
            f"headword={self._format_pair(self.headword, self.headword_support)} "
            f"headword_hist={self._format_histogram(self.headword_histogram)} "
            f"continuation={self._format_pair(self.continuation, self.continuation_support)} "
            f"continuation_hist={self._format_histogram(self.continuation_histogram)} "
            f"homonym={self._format_pair(self.homonym, self.homonym_support)} "
            f"homonym_hist={self._format_histogram(self.homonym_histogram)}"
        )


@dataclass(frozen=True)
class InferredStartGeometry:
    centers: tuple[int, ...]
    ranges: tuple[tuple[int, int], ...]
    observations: tuple[int, ...]
    headword: tuple[int, ...] = ()
    continuation: tuple[int, ...] = ()
    homonym: tuple[int, ...] = ()
    headword_support: tuple[int, ...] = ()
    continuation_support: tuple[int, ...] = ()
    homonym_support: tuple[int, ...] = ()
    headword_histogram: tuple[tuple[int, int], ...] = ()
    continuation_histogram: tuple[tuple[int, int], ...] = ()
    homonym_histogram: tuple[tuple[int, int], ...] = ()


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


def _histogram(entries: Iterable[int]) -> tuple[tuple[int, int], ...]:
    counts = Counter(int(x) for x in entries)
    return tuple(sorted(counts.items()))


def _adjacent_start_pair(entries: Iterable[int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Choose one strict adjacent raster pair and report support for each x.

    A row-start family is represented by exactly two neighbouring raster x
    positions. We score adjacent pairs directly instead of choosing two unrelated
    frequency peaks. Pair score is the number of observations explained by either
    member. Ties prefer evidence on both positions, then balance, then leftmost.
    """
    counts = Counter(int(x) for x in entries)
    if not counts:
        return (), ()

    lo = min(counts) - 1
    hi = max(counts)
    candidates: list[tuple[tuple[int, int, int, int], tuple[int, int]]] = []
    for x in range(lo, hi + 1):
        left = counts[x]
        right = counts[x + 1]
        score = left + right
        if score == 0:
            continue
        both = int(left > 0 and right > 0)
        balance = min(left, right)
        candidates.append(((score, both, balance, -x), (x, x + 1)))

    _rank, pair = max(candidates, key=lambda item: item[0])
    support = (counts[pair[0]], counts[pair[1]])
    return pair, support


def infer_page_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer strict row-start x values for one already selected column."""
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

    pair_results = tuple(_adjacent_start_pair(entries) for entries in class_entries)
    starts = tuple(pair for pair, _support in pair_results)
    supports = tuple(support for _pair, support in pair_results)
    histograms = tuple(_histogram(entries) for entries in class_entries)

    homonym: tuple[int, ...] = ()
    headword: tuple[int, ...] = ()
    continuation: tuple[int, ...] = ()
    homonym_support: tuple[int, ...] = ()
    headword_support: tuple[int, ...] = ()
    continuation_support: tuple[int, ...] = ()
    homonym_histogram: tuple[tuple[int, int], ...] = ()
    headword_histogram: tuple[tuple[int, int], ...] = ()
    continuation_histogram: tuple[tuple[int, int], ...] = ()

    if len(starts) >= 3:
        homonym, headword, continuation = starts[:3]
        homonym_support, headword_support, continuation_support = supports[:3]
        homonym_histogram, headword_histogram, continuation_histogram = histograms[:3]
    elif len(starts) == 2:
        headword, continuation = starts
        headword_support, continuation_support = supports
        headword_histogram, continuation_histogram = histograms
    elif len(starts) == 1:
        headword = starts[0]
        headword_support = supports[0]
        headword_histogram = histograms[0]

    strict_tuple = tuple(sorted(set(homonym + headword + continuation)))
    strict = StartValues(
        strict_tuple,
        headword=headword,
        continuation=continuation,
        homonym=homonym,
        headword_support=headword_support,
        continuation_support=continuation_support,
        homonym_support=homonym_support,
        headword_histogram=headword_histogram,
        continuation_histogram=continuation_histogram,
        homonym_histogram=homonym_histogram,
    )
    return InferredStartGeometry(
        centers=strict,
        ranges=tuple((x, x) for x in strict_tuple),
        observations=tuple(all_entries),
        headword=headword,
        continuation=continuation,
        homonym=homonym,
        headword_support=headword_support,
        continuation_support=continuation_support,
        homonym_support=homonym_support,
        headword_histogram=headword_histogram,
        continuation_histogram=continuation_histogram,
        homonym_histogram=homonym_histogram,
    )
