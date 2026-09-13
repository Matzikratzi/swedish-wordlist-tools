from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_baseline_up import BaselineMatch, CompiledGlyph, CompiledGlyphLibrary, Pixel
from .ocr_column_left_profile import ColumnLeftProfile


TranslateXRange = tuple[int, int]


@dataclass(frozen=True)
class FirstGlyphSearch:
    y: int | None
    candidates: tuple[BaselineMatch, ...]


def _x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def _placed_pixels(item: CompiledGlyph, *, tx: int, baseline: int) -> frozenset[Pixel]:
    return frozenset((tx + x, baseline + y) for x, y in item.model.pixels)


def _candidate_rows(candidate: BaselineMatch) -> dict[int, tuple[int, ...]]:
    rows: dict[int, list[int]] = {}
    for x, y in candidate.pixels:
        rows.setdefault(y, []).append(x)
    return {y: tuple(sorted(xs)) for y, xs in rows.items()}


def _pick_unique_maximal(candidates: Iterable[BaselineMatch]) -> BaselineMatch | None:
    rows = list(candidates)
    if not rows:
        return None
    maximal = [
        hit
        for hit in rows
        if not any(hit.pixels < other.pixels for other in rows if other is not hit)
    ]
    distinct = {hit.pixels for hit in maximal}
    if len(distinct) != 1:
        return None
    target = next(iter(distinct))
    equivalent = [hit for hit in maximal if hit.pixels == target]
    return max(equivalent, key=lambda hit: (len(hit.pixels), hit.model.sources))


def _profile_at(
    page_y: int,
    *,
    black_by_y: Mapping[int, Iterable[int]],
    left_profile: ColumnLeftProfile | None,
) -> int | None:
    if left_profile is not None:
        return left_profile.at(page_y)
    row_xs = tuple(black_by_y.get(page_y, ()))
    return min(row_xs) if row_xs else None


def _default_scan_bottom(
    *,
    row_top: int,
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    left_profile: ColumnLeftProfile | None,
) -> int:
    """Bound an unknown text row from glyph geometry, never from facit."""
    source_bottom = (
        left_profile.bottom
        if left_profile is not None
        else (max(black_by_y) + 1 if black_by_y else row_top)
    )
    max_glyph_height = max(
        (max(item.rows) - min(item.rows) + 1 for item in library.models if item.rows),
        default=1,
    )
    return min(source_bottom, row_top + max_glyph_height)


def _row_clearance(item: CompiledGlyph, rel_y: int) -> int:
    """Guaranteed empty prefix from the glyph's physical left edge.

    For an ink row this is the distance to its first black pixel. For a row
    inside the glyph's vertical extent with no ink, the whole glyph width is
    guaranteed empty. This is the code-level form of the compact negative
    'gap depth' notation discussed during development.
    """
    row = item.rows.get(rel_y)
    if row is None:
        return item.width
    return row[0] - item.min_x


def _profile_compatible(
    item: CompiledGlyph,
    *,
    tx: int,
    baseline: int,
    observed: Mapping[int, int | None],
) -> tuple[bool, int, int]:
    """Check a glyph against the observed lower-envelope left profile.

    A candidate front left of the observed page front is impossible. Equality
    means this glyph owns/explains the page-profile point. A candidate front to
    the right is allowed because another glyph may own the lower envelope.
    Empty glyph rows are gaps and impose no page-envelope equality.
    """
    min_rel = min(item.rows)
    max_rel = max(item.rows)
    explained = 0
    gap_rows = 0
    physical_left = tx + item.min_x

    for page_y, observed_x in observed.items():
        rel_y = page_y - baseline
        if rel_y < min_rel or rel_y > max_rel:
            continue
        row = item.rows.get(rel_y)
        if row is None:
            gap_rows += 1
            continue
        candidate_front = physical_left + _row_clearance(item, rel_y)
        if observed_x is None:
            return False, explained, gap_rows
        if candidate_front < observed_x:
            return False, explained, gap_rows
        if candidate_front == observed_x:
            explained += 1

    return True, explained, gap_rows


def _seed_from_record_row(
    *,
    page_y: int,
    observed_x: int,
    observed: Mapping[int, int | None],
    black: set[Pixel],
    library: CompiledGlyphLibrary,
    row_top: int,
    start_ranges: tuple[TranslateXRange, ...],
) -> tuple[tuple[CompiledGlyph, BaselineMatch, int, int], ...]:
    """Seed candidates from the actual horizontal raster at a left record.

    Unlike the previous two-y experiment, the record row itself supplies more
    than one bit: every black pixel in the model's horizontal row must already
    exist in the source. Full 2-D verification is deliberately postponed.
    """
    found: dict[tuple[int, int, int], tuple[CompiledGlyph, BaselineMatch, int, int]] = {}

    for item in library.models:
        for rel_y, model_row in item.rows.items():
            tx = observed_x - model_row[0]
            physical_left = tx + item.min_x
            if not _x_allowed(physical_left, start_ranges):
                continue

            baseline = page_y - rel_y
            key = (id(item.model), tx, baseline)
            if key in found:
                continue

            # The complete horizontal glyph row must be present before this
            # model is allowed to become a live profile candidate.
            if any((tx + x, page_y) not in black for x in model_row):
                continue

            placed = _placed_pixels(item, tx=tx, baseline=baseline)
            if not placed or min(y for _x, y in placed) < row_top:
                continue

            candidate = BaselineMatch(
                model=item.model,
                tx=tx,
                baseline=baseline,
                pixels=placed,
                discovered_y=page_y,
            )
            compatible, explained, gaps = _profile_compatible(
                item,
                tx=tx,
                baseline=baseline,
                observed=observed,
            )
            if not compatible or explained == 0:
                continue
            found[key] = (item, candidate, explained, gaps)

    return tuple(
        sorted(
            found.values(),
            key=lambda entry: (
                entry[1].left,
                -entry[2],
                -len(entry[1].pixels),
                -entry[1].model.sources,
                entry[1].model.label,
                entry[1].model.style,
                entry[1].baseline,
            ),
        )
    )


def _trace_candidate(
    prefix: str,
    event: str,
    candidate: BaselineMatch,
    **fields: object,
) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"{prefix} first-glyph-{event}: label={candidate.model.label!r} "
        f"style={candidate.model.style} left={candidate.left} right={candidate.right} "
        f"baseline={candidate.baseline} discovered_y={candidate.discovered_y} "
        f"pixels={len(candidate.pixels)}" + (f" {extra}" if extra else ""),
        flush=True,
    )


def first_glyph_top_down(
    black: set[Pixel],
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    row_top: int,
    row_bottom: int | None = None,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    left_profile: ColumnLeftProfile | None = None,
    trace: bool = False,
    trace_prefix: str = "directional-trace",
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the first glyph by profile history, left records and raster rows.

    Scan down from row_top and merely remember profile values until a new
    leftward record reaches a plausible row-start x. At that point seed from
    the full horizontal raster row, match the candidate profile back upward,
    then continue downward while candidates survive. Only the final survivors
    receive an exact 2-D subset test.
    """
    trace = trace or os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return None, FirstGlyphSearch(y=None, candidates=())

    scan_bottom = (
        int(row_bottom)
        if row_bottom is not None
        else _default_scan_bottom(
            row_top=row_top,
            black_by_y=black_by_y,
            library=library,
            left_profile=left_profile,
        )
    )
    if scan_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    observed: dict[int, int | None] = {}
    best_x: int | None = None
    live: dict[tuple[int, int, int], tuple[CompiledGlyph, BaselineMatch]] = {}
    seed_y: int | None = None

    if trace:
        print(
            f"{trace_prefix} first-glyph-profile-scan: band={row_top}..{scan_bottom - 1}",
            flush=True,
        )

    for page_y in range(row_top, scan_bottom):
        profile_x = _profile_at(page_y, black_by_y=black_by_y, left_profile=left_profile)
        observed[page_y] = profile_x
        is_record = profile_x is not None and (best_x is None or profile_x < best_x)
        if is_record:
            best_x = profile_x

        if trace:
            shown = "inf" if profile_x is None else str(profile_x)
            print(
                f"{trace_prefix} first-glyph-profile: y={page_y} x={shown} "
                f"record={is_record} live={len(live)}",
                flush=True,
            )

        if not live:
            # A profile value outside every plausible start range is history,
            # not a seed. We keep scanning until a new left record enters one.
            if not is_record or profile_x is None or not _x_allowed(profile_x, ranges):
                continue

            seeded = _seed_from_record_row(
                page_y=page_y,
                observed_x=profile_x,
                observed=observed,
                black=black,
                library=library,
                row_top=row_top,
                start_ranges=ranges,
            )
            if trace:
                print(
                    f"{trace_prefix} first-glyph-record-seed: y={page_y} x={profile_x} "
                    f"candidates={len(seeded)}",
                    flush=True,
                )
                for item, candidate, explained, gaps in seeded:
                    rel_y = page_y - candidate.baseline
                    _trace_candidate(
                        trace_prefix,
                        "proposal",
                        candidate,
                        explained=explained,
                        gaps=gaps,
                        clearance=_row_clearance(item, rel_y),
                    )
            if not seeded:
                continue

            seed_y = page_y
            live = {
                (id(candidate.model), candidate.tx, candidate.baseline): (item, candidate)
                for item, candidate, _explained, _gaps in seeded
            }
            continue

        # Feed each new y observation into the lower-envelope matcher. A gap
        # (no row in the model) stays live; a model front left of the observed
        # front dies; equality explains/owns that profile point.
        next_live: dict[tuple[int, int, int], tuple[CompiledGlyph, BaselineMatch]] = {}
        for key, (item, candidate) in live.items():
            compatible, explained, gaps = _profile_compatible(
                item,
                tx=candidate.tx,
                baseline=candidate.baseline,
                observed=observed,
            )
            if compatible:
                next_live[key] = (item, candidate)
            if trace:
                _trace_candidate(
                    trace_prefix,
                    "live" if compatible else "dead",
                    candidate,
                    y=page_y,
                    explained=explained,
                    gaps=gaps,
                )
        live = next_live
        if not live:
            # Continue scanning. A later, still farther-left record may seed a
            # different glyph interpretation; the collected history is kept.
            continue

    # Expensive exact raster verification happens only here, on the profile
    # survivors rather than on every translated model proposal.
    exact: list[BaselineMatch] = []
    for item, candidate in live.values():
        if candidate.pixels.issubset(black):
            exact.append(candidate)
            if trace:
                _trace_candidate(trace_prefix, "2d-pass", candidate)
        elif trace:
            _trace_candidate(trace_prefix, "2d-fail", candidate)

    candidates = tuple(
        sorted(
            exact,
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
                hit.baseline,
            ),
        )
    )
    hit = _pick_unique_maximal(candidates)
    if trace:
        accepted = repr(hit.model.label) if hit is not None else None
        print(
            f"{trace_prefix} first-glyph-pick: seed_y={seed_y} "
            f"profile_survivors={len(live)} exact={len(candidates)} accepted={accepted}",
            flush=True,
        )

    return hit, FirstGlyphSearch(y=seed_y, candidates=candidates)
