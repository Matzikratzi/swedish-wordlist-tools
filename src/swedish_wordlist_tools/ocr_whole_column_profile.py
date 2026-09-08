from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


ProfileValue = int | None
ProfileSignature = tuple[ProfileValue, ...]
TranslateXRange = tuple[int, int]


@dataclass(frozen=True)
class IndexedProfileFragment:
    model: GlyphModel
    signature: ProfileSignature
    model_start_y: int
    anchor_x: int
    anchor_row: int
    rows: int
    ink_rows: int
    wildcard_rows: frozenset[int] = frozenset()


@dataclass(frozen=True)
class ProfileFragmentIndex:
    exact: dict[tuple[int, ProfileSignature], tuple[IndexedProfileFragment, ...]]
    wildcard_by_rows: dict[int, tuple[IndexedProfileFragment, ...]]


@dataclass(frozen=True)
class ProfileExactHit:
    model: GlyphModel
    x: int
    baseline: int
    profile_start_y: int
    profile_end_y: int
    profile_rows: int
    profile_ink_rows: int

    @property
    def top_y(self) -> int:
        return self.baseline + self.model.min_y

    @property
    def bottom_y(self) -> int:
        return self.baseline + self.model.max_y


@dataclass(frozen=True)
class ProfileRowStart:
    index: int
    hit: ProfileExactHit
    search_from_y: int
    search_to_y: int
    next_search_y: int


def whole_column_left_profile(
    black: set[tuple[int, int]],
    *,
    min_y: int,
    max_y: int,
    max_x: int,
    min_x: int = 0,
) -> tuple[ProfileValue, ...]:
    """Return the leftmost ink x for every physical pixel row in a column."""
    if max_y < min_y:
        raise ValueError("max_y must be >= min_y")
    if max_x < min_x:
        raise ValueError("max_x must be >= min_x")
    left: list[int | None] = [None] * (max_y - min_y + 1)
    for x, y in black:
        if y < min_y or y > max_y or x < min_x or x > max_x:
            continue
        offset = y - min_y
        previous = left[offset]
        if previous is None or x < previous:
            left[offset] = x
    return tuple(left)


def _model_left_profile(model: GlyphModel) -> tuple[ProfileValue, ...]:
    by_y: dict[int, int] = {}
    for x, y in model.pixels:
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(by_y.get(y) for y in range(model.min_y, model.max_y + 1))


def _normalise_profile(values: tuple[ProfileValue, ...]) -> tuple[ProfileSignature, int] | None:
    anchor = next((value for value in values if value is not None), None)
    if anchor is None:
        return None
    return tuple(None if value is None else value - anchor for value in values), int(anchor)


def _small_internal_hole_rows(values: tuple[ProfileValue, ...], *, max_gap: int) -> frozenset[int]:
    """Return blank rows that form small, bounded gaps between ink rows.

    Detached marks (i, j, :, ;, umlauts, etc.) create real blank raster rows in
    a glyph's left profile. In the whole-column profile another glyph can be the
    leftmost ink in those rows, so those positions must not be compared exactly.
    Only internal gaps no taller than the glyph width are treated as wildcards;
    edge blanks and larger gaps remain significant.
    """
    if max_gap <= 0:
        return frozenset()
    wild: set[int] = set()
    i = 0
    while i < len(values):
        if values[i] is not None:
            i += 1
            continue
        start = i
        while i < len(values) and values[i] is None:
            i += 1
        end = i
        bounded = start > 0 and end < len(values) and values[start - 1] is not None and values[end] is not None
        if bounded and end - start <= max_gap:
            wild.update(range(start, end))
    return frozenset(wild)


def build_profile_fragment_index(
    models: Iterable[GlyphModel],
    *,
    min_rows: int = 2,
    max_rows: int = 20,
    min_ink_rows: int = 2,
) -> ProfileFragmentIndex:
    """Index exact and small-hole-tolerant partial glyph left profiles."""
    if min_rows <= 0 or max_rows < min_rows:
        raise ValueError("invalid profile row limits")
    if min_ink_rows <= 0:
        raise ValueError("min_ink_rows must be positive")
    exact: dict[tuple[int, ProfileSignature], list[IndexedProfileFragment]] = defaultdict(list)
    wildcard_by_rows: dict[int, list[IndexedProfileFragment]] = defaultdict(list)
    for model in models:
        profile = _model_left_profile(model)
        model_start_x = min(x for x, _y in model.pixels)
        for rows in range(min_rows, min(max_rows, len(profile)) + 1):
            for offset in range(0, len(profile) - rows + 1):
                fragment = profile[offset : offset + rows]
                ink_rows = sum(value is not None for value in fragment)
                if ink_rows < min_ink_rows:
                    continue
                if model_start_x not in fragment:
                    continue
                normalised = _normalise_profile(fragment)
                if normalised is None:
                    continue
                signature, anchor_x = normalised
                anchor_row = next(i for i, value in enumerate(fragment) if value is not None)
                wildcard_rows = _small_internal_hole_rows(fragment, max_gap=model.width)
                indexed = IndexedProfileFragment(
                    model=model,
                    signature=signature,
                    model_start_y=model.min_y + offset,
                    anchor_x=anchor_x,
                    anchor_row=anchor_row,
                    rows=rows,
                    ink_rows=ink_rows,
                    wildcard_rows=wildcard_rows,
                )
                if wildcard_rows:
                    wildcard_by_rows[rows].append(indexed)
                else:
                    exact[(rows, signature)].append(indexed)
    return ProfileFragmentIndex(
        exact={key: tuple(value) for key, value in exact.items()},
        wildcard_by_rows={key: tuple(value) for key, value in wildcard_by_rows.items()},
    )


def _translate_x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def _wildcard_profile_match(source: tuple[ProfileValue, ...], indexed: IndexedProfileFragment) -> int | None:
    """Return source anchor x when fixed profile rows match.

    Rows belonging to a small internal model hole are ignored completely: they
    may be blank or may contain left-edge ink from another glyph. All other rows
    remain exact, including None rows that are not a small bounded hole.
    """
    source_anchor = source[indexed.anchor_row]
    if source_anchor is None:
        return None
    for row, expected in enumerate(indexed.signature):
        if row in indexed.wildcard_rows:
            continue
        actual = source[row]
        if expected is None:
            if actual is not None:
                return None
        elif actual is None or actual - source_anchor != expected:
            return None
    return int(source_anchor)


def profile_guided_exact_hits(
    black: set[tuple[int, int]],
    profile: tuple[ProfileValue, ...],
    *,
    profile_min_y: int,
    fragment_index: ProfileFragmentIndex,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    min_rows: int = 2,
    max_rows: int = 20,
) -> tuple[ProfileExactHit, ...]:
    """Find profile substrings, then verify every complete glyph pixel in 2D."""
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges or any(lo > hi for lo, hi in ranges):
        raise ValueError("allowed translate-x ranges must be non-empty and ordered")
    best: dict[tuple[int, int, int], ProfileExactHit] = {}

    def consider(indexed: IndexedProfileFragment, source_anchor_x: int, source_start_y: int) -> None:
        tx = source_anchor_x - indexed.anchor_x
        if not _translate_x_allowed(tx, ranges):
            return
        baseline = source_start_y - indexed.model_start_y
        if not all((tx + x, baseline + y) in black for x, y in indexed.model.pixels):
            return
        key = (id(indexed.model), tx, baseline)
        hit = ProfileExactHit(
            model=indexed.model,
            x=tx,
            baseline=baseline,
            profile_start_y=source_start_y,
            profile_end_y=source_start_y + indexed.rows - 1,
            profile_rows=indexed.rows,
            profile_ink_rows=indexed.ink_rows,
        )
        previous = best.get(key)
        if previous is None or (
            hit.profile_ink_rows,
            hit.profile_rows,
            -hit.profile_start_y,
        ) > (
            previous.profile_ink_rows,
            previous.profile_rows,
            -previous.profile_start_y,
        ):
            best[key] = hit

    upper_rows = min(max_rows, len(profile))
    for rows in range(min_rows, upper_rows + 1):
        wildcards = fragment_index.wildcard_by_rows.get(rows, ())
        for offset in range(0, len(profile) - rows + 1):
            source = profile[offset : offset + rows]
            source_start_y = profile_min_y + offset
            normalised = _normalise_profile(source)
            if normalised is not None:
                signature, source_anchor_x = normalised
                for indexed in fragment_index.exact.get((rows, signature), ()):
                    consider(indexed, source_anchor_x, source_start_y)
            for indexed in wildcards:
                source_anchor_x = _wildcard_profile_match(source, indexed)
                if source_anchor_x is not None:
                    consider(indexed, source_anchor_x, source_start_y)

    return tuple(
        sorted(
            best.values(),
            key=lambda hit: (
                hit.baseline,
                hit.x,
                -hit.profile_ink_rows,
                -hit.profile_rows,
                -len(hit.model.pixels),
                hit.model.label,
                hit.model.style,
            ),
        )
    )


def _placed_pixels(hit: ProfileExactHit) -> frozenset[tuple[int, int]]:
    return frozenset((hit.x + x, hit.baseline + y) for x, y in hit.model.pixels)


def _baseline_evidence_key(hits: Iterable[ProfileExactHit]) -> tuple[int, int, int, int, int]:
    rows = tuple(hits)
    covered: set[tuple[int, int]] = set()
    for hit in rows:
        covered.update(_placed_pixels(hit))
    distinct_x = len({hit.x for hit in rows})
    max_model_pixels = max((len(hit.model.pixels) for hit in rows), default=0)
    max_profile_ink_rows = max((hit.profile_ink_rows for hit in rows), default=0)
    max_profile_rows = max((hit.profile_rows for hit in rows), default=0)
    return len(covered), distinct_x, max_model_pixels, max_profile_ink_rows, max_profile_rows


def walk_profile_row_starts(
    hits: Iterable[ProfileExactHit],
    *,
    start_y: int,
    end_y: int,
    max_row_distance: int = 20,
    min_baseline_delta: int = 8,
) -> tuple[ProfileRowStart, ...]:
    """Walk downward, resolving nearby baseline aliases by combined evidence."""
    if max_row_distance <= 0:
        raise ValueError("max_row_distance must be positive")
    if min_baseline_delta <= 0:
        raise ValueError("min_baseline_delta must be positive")
    rows = tuple(hits)
    out: list[ProfileRowStart] = []
    search_y = int(start_y)
    previous_baseline: int | None = None
    while search_y <= end_y:
        limit_y = min(end_y, search_y + max_row_distance)
        minimum_baseline = None if previous_baseline is None else previous_baseline + min_baseline_delta
        legal = [
            hit
            for hit in rows
            if search_y <= hit.profile_start_y <= limit_y
            and (minimum_baseline is None or hit.baseline >= minimum_baseline)
        ]
        if not legal:
            break

        by_baseline: dict[int, list[ProfileExactHit]] = defaultdict(list)
        for hit in legal:
            by_baseline[hit.baseline].append(hit)
        first_baseline = min(by_baseline)
        alias_limit = first_baseline + min_baseline_delta - 1
        candidate_baselines = [baseline for baseline in by_baseline if first_baseline <= baseline <= alias_limit]
        chosen_baseline = max(
            candidate_baselines,
            key=lambda baseline: (_baseline_evidence_key(by_baseline[baseline]), -baseline),
        )
        same_baseline = by_baseline[chosen_baseline]
        same_baseline.sort(
            key=lambda hit: (
                hit.x,
                -hit.profile_ink_rows,
                -hit.profile_rows,
                -len(hit.model.pixels),
                hit.model.label,
                hit.model.style,
            )
        )
        found = same_baseline[0]
        next_search_y = max(search_y + 1, found.baseline + 1)
        out.append(
            ProfileRowStart(
                index=len(out),
                hit=found,
                search_from_y=search_y,
                search_to_y=limit_y,
                next_search_y=next_search_y,
            )
        )
        previous_baseline = found.baseline
        search_y = next_search_y
    return tuple(out)
