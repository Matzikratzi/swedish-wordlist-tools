from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_glyph_matcher import GlyphModel


Pixel = tuple[int, int]


@dataclass(frozen=True)
class CompiledGlyph:
    model: GlyphModel
    min_x: int
    max_x: int
    rows: dict[int, tuple[int, ...]]

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1


@dataclass(frozen=True)
class BaselineMatch:
    model: GlyphModel
    tx: int
    baseline: int
    pixels: frozenset[Pixel]
    discovered_y: int

    @property
    def left(self) -> int:
        return min(x for x, _y in self.pixels)

    @property
    def right(self) -> int:
        return max(x for x, _y in self.pixels)


class CompiledGlyphLibrary:
    """Geometry compiled once for cheap repeated row matching.

    ``by_rel_y`` is the important index for the baseline-up walk. At a page
    raster y and known baseline we know rel_y immediately, so only models that
    actually contain ink on that relative glyph row need to be considered.
    """

    def __init__(self, models: Iterable[GlyphModel]):
        compiled: list[CompiledGlyph] = []
        by_rel_y: dict[int, list[CompiledGlyph]] = defaultdict(list)
        for model in models:
            xs = [x for x, _y in model.pixels]
            rows_mut: dict[int, list[int]] = defaultdict(list)
            for x, y in model.pixels:
                rows_mut[y].append(x)
            rows = {y: tuple(sorted(row_xs)) for y, row_xs in rows_mut.items()}
            item = CompiledGlyph(
                model=model,
                min_x=min(xs),
                max_x=max(xs),
                rows=rows,
            )
            compiled.append(item)
            for rel_y in rows:
                by_rel_y[rel_y].append(item)

        self.models = tuple(compiled)
        self.by_rel_y = {rel_y: tuple(items) for rel_y, items in by_rel_y.items()}
        self.max_up = max((-item.model.min_y for item in compiled), default=0)
        self.max_down = max((item.model.max_y for item in compiled), default=0)


class ResidualInk:
    """Mutable residual pixels with a page-y index maintained incrementally."""

    def __init__(self, black: Iterable[Pixel]):
        self.pixels: set[Pixel] = set(black)
        rows: dict[int, set[int]] = defaultdict(set)
        for x, y in self.pixels:
            rows[y].add(x)
        self.rows: dict[int, set[int]] = dict(rows)

    def consume(self, pixels: Iterable[Pixel]) -> None:
        for x, y in pixels:
            if (x, y) not in self.pixels:
                continue
            self.pixels.remove((x, y))
            row = self.rows.get(y)
            if row is None:
                continue
            row.discard(x)
            if not row:
                del self.rows[y]

    def row(self, y: int) -> set[int]:
        return self.rows.get(y, set())


def black_by_y(black: Iterable[Pixel]) -> dict[int, tuple[int, ...]]:
    rows: dict[int, list[int]] = defaultdict(list)
    for x, y in black:
        rows[y].append(x)
    return {y: tuple(sorted(xs)) for y, xs in rows.items()}


def _placed_pixels(item: CompiledGlyph, *, tx: int, baseline: int) -> frozenset[Pixel]:
    return frozenset((tx + x, baseline + y) for x, y in item.model.pixels)


def _candidate_key(item: CompiledGlyph, tx: int, baseline: int) -> tuple[int, int, int]:
    return id(item.model), tx, baseline


def baseline_up_candidates(
    remaining: set[Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    after_left: int,
    column_right: int,
) -> tuple[BaselineMatch, ...]:
    """Find exact next-glyph candidates by walking upward from the baseline.

    No candidate x translation is scanned across the column. A translation is
    proposed only when an actual residual page pixel can coincide with an
    actual model pixel on the corresponding relative raster row. Every proposal
    is then verified as an exact pixel subset of ``remaining``.

    The whole short baseline..row_top interval is visited before choosing a
    winner. That keeps an earlier punctuation/detached glyph from being skipped
    merely because a farther-right glyph has ink on the baseline.
    """
    if baseline < row_top:
        return ()

    seen: set[tuple[int, int, int]] = set()
    found: list[BaselineMatch] = []

    stop_y = max(row_top, baseline - library.max_up)
    for page_y in range(baseline, stop_y - 1, -1):
        observed_xs = remaining_by_y.get(page_y, ())
        rel_y = page_y - baseline
        possible_models = library.by_rel_y.get(rel_y, ())
        if not possible_models:
            continue

        for item in possible_models:
            model_row = item.rows[rel_y]
            for observed_x in observed_xs:
                if observed_x >= column_right:
                    continue
                for model_x in model_row:
                    tx = observed_x - model_x
                    physical_left = tx + item.min_x
                    physical_right = tx + item.max_x
                    if physical_left <= after_left or physical_right >= column_right:
                        continue
                    key = _candidate_key(item, tx, baseline)
                    if key in seen:
                        continue
                    seen.add(key)
                    placed = _placed_pixels(item, tx=tx, baseline=baseline)
                    if placed.issubset(remaining):
                        found.append(
                            BaselineMatch(
                                model=item.model,
                                tx=tx,
                                baseline=baseline,
                                pixels=placed,
                                discovered_y=page_y,
                            )
                        )

    return tuple(
        sorted(
            found,
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )


def pick_leftmost_unique_maximal(candidates: Iterable[BaselineMatch]) -> BaselineMatch | None:
    rows = list(candidates)
    if not rows:
        return None
    left = min(hit.left for hit in rows)
    rows = [hit for hit in rows if hit.left == left]

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
    return max(
        equivalent,
        key=lambda hit: (len(hit.pixels), hit.model.sources, hit.model.label, hit.model.style),
    )


def find_next_baseline_up(
    remaining: set[Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    after_left: int,
    column_right: int,
) -> tuple[BaselineMatch | None, tuple[BaselineMatch, ...]]:
    candidates = baseline_up_candidates(
        remaining,
        remaining_by_y,
        library,
        baseline=baseline,
        row_top=row_top,
        after_left=after_left,
        column_right=column_right,
    )
    return pick_leftmost_unique_maximal(candidates), candidates
