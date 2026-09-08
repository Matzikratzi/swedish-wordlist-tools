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
    rows: int
    ink_rows: int


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
    """Return the leftmost ink x for every physical pixel row in a column.

    The result is dense: blank raster rows are represented by ``None``. It is
    deliberately computed once for the whole column so later searches only scan
    this small one-dimensional profile instead of rescanning page pixels.
    """
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


def build_profile_fragment_index(
    models: Iterable[GlyphModel],
    *,
    min_rows: int = 2,
    max_rows: int = 20,
    min_ink_rows: int = 2,
) -> dict[tuple[int, ProfileSignature], tuple[IndexedProfileFragment, ...]]:
    """Index partial glyph left profiles that include a real start-x pixel.

    A fragment may be only part of a glyph, but it must contain at least one
    raster row where the glyph reaches its own leftmost x. That is the hard
    anchor which prevents an arbitrary interior piece from being treated as a
    row-start glyph.
    """
    if min_rows <= 0 or max_rows < min_rows:
        raise ValueError("invalid profile row limits")
    if min_ink_rows <= 0:
        raise ValueError("min_ink_rows must be positive")
    buckets: dict[tuple[int, ProfileSignature], list[IndexedProfileFragment]] = defaultdict(list)
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
                indexed = IndexedProfileFragment(
                    model=model,
                    signature=signature,
                    model_start_y=model.min_y + offset,
                    anchor_x=anchor_x,
                    rows=rows,
                    ink_rows=ink_rows,
                )
                buckets[(rows, signature)].append(indexed)
    return {key: tuple(value) for key, value in buckets.items()}


def _translate_x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def profile_guided_exact_hits(
    black: set[tuple[int, int]],
    profile: tuple[ProfileValue, ...],
    *,
    profile_min_y: int,
    fragment_index: dict[tuple[int, ProfileSignature], tuple[IndexedProfileFragment, ...]],
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    min_rows: int = 2,
    max_rows: int = 20,
) -> tuple[ProfileExactHit, ...]:
    """Find partial profile matches, then verify the complete glyph in 2D ink.

    The cheap stage is a substring lookup in the already-built whole-column
    left profile. Only candidates whose translated glyph start x lies in one
    of the typographic start ranges reach the expensive stage. The expensive
    stage requires every facit pixel of the placed glyph to exist in the page,
    including pixels behind the visible left-edge profile.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges or any(lo > hi for lo, hi in ranges):
        raise ValueError("allowed translate-x ranges must be non-empty and ordered")
    best: dict[tuple[int, int, int], ProfileExactHit] = {}
    upper_rows = min(max_rows, len(profile))
    for rows in range(min_rows, upper_rows + 1):
        for offset in range(0, len(profile) - rows + 1):
            source = profile[offset : offset + rows]
            normalised = _normalise_profile(source)
            if normalised is None:
                continue
            signature, source_anchor_x = normalised
            for indexed in fragment_index.get((rows, signature), ()):
                tx = source_anchor_x - indexed.anchor_x
                if not _translate_x_allowed(tx, ranges):
                    continue
                source_start_y = profile_min_y + offset
                baseline = source_start_y - indexed.model_start_y
                if not all((tx + x, baseline + y) in black for x, y in indexed.model.pixels):
                    continue
                key = (id(indexed.model), tx, baseline)
                hit = ProfileExactHit(
                    model=indexed.model,
                    x=tx,
                    baseline=baseline,
                    profile_start_y=source_start_y,
                    profile_end_y=source_start_y + rows - 1,
                    profile_rows=rows,
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
    """Score one baseline without counting overlapping alias matches twice.

    A tall glyph can contain the complete bitmap of a shorter glyph at several
    vertical offsets. Those are real exact submatches, not search errors. A real
    text baseline normally has corroboration from several start-zone glyphs, so
    score the union of verified glyph pixels and distinct x anchors before the
    strongest single profile fragment.
    """
    rows = tuple(hits)
    covered: set[tuple[int, int]] = set()
    for hit in rows:
        covered.update(_placed_pixels(hit))
    distinct_x = len({hit.x for hit in rows})
    max_model_pixels = max((len(hit.model.pixels) for hit in rows), default=0)
    max_profile_ink_rows = max((hit.profile_ink_rows for hit in rows), default=0)
    max_profile_rows = max((hit.profile_rows for hit in rows), default=0)
    return (
        len(covered),
        distinct_x,
        max_model_pixels,
        max_profile_ink_rows,
        max_profile_rows,
    )


def walk_profile_row_starts(
    hits: Iterable[ProfileExactHit],
    *,
    start_y: int,
    end_y: int,
    max_row_distance: int = 20,
    min_baseline_delta: int = 8,
) -> tuple[ProfileRowStart, ...]:
    """Walk downward, resolving nearby baseline aliases by combined evidence.

    Profile fragments may appear in surprising vertical order (for example the
    top of a late capital may be the first visible ink in ``¤aicvP``). A tall
    glyph may also contain an exact shorter glyph at several vertical offsets.
    Baselines closer than ``min_baseline_delta`` cannot represent separate text
    rows, so the walker first forms the earliest such baseline cluster and picks
    the baseline with the strongest combined exact-glyph evidence. The leftmost
    verified glyph on that winning baseline represents the row start.
    """
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
        candidate_baselines = [
            baseline for baseline in by_baseline
            if first_baseline <= baseline <= alias_limit
        ]
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
