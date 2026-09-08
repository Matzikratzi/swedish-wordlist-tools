from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


TranslateXRange = tuple[int, int]
RowInk = dict[int, frozenset[int]]


@dataclass(frozen=True)
class SurvivalCandidate:
    model: GlyphModel
    x: int
    baseline: int
    seed_y: int
    survived_to_y: int

    @property
    def top_y(self) -> int:
        return self.baseline + self.model.min_y

    @property
    def bottom_y(self) -> int:
        return self.baseline + self.model.max_y


@dataclass(frozen=True)
class SurvivalStep:
    y: int
    before: int
    after: int
    died: int


@dataclass(frozen=True)
class SurvivalResult:
    completed: tuple[SurvivalCandidate, ...]
    steps: tuple[SurvivalStep, ...]
    seeded: int


def _translate_x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def _ink_by_y(black: set[tuple[int, int]]) -> RowInk:
    by_y: dict[int, set[int]] = {}
    for x, y in black:
        by_y.setdefault(y, set()).add(x)
    return {y: frozenset(xs) for y, xs in by_y.items()}


def _model_rows(model: GlyphModel) -> dict[int, frozenset[int]]:
    by_y: dict[int, set[int]] = {}
    for x, y in model.pixels:
        by_y.setdefault(y, set()).add(x)
    return {y: frozenset(xs) for y, xs in by_y.items()}


def _internal_gap_rows(model: GlyphModel) -> frozenset[int]:
    occupied = {y for _x, y in model.pixels}
    return frozenset(y for y in range(model.min_y + 1, model.max_y) if y not in occupied)


def _row_compatible(
    ink_by_y: RowInk,
    *,
    model: GlyphModel,
    model_rows: dict[int, frozenset[int]],
    gap_rows: frozenset[int],
    x: int,
    baseline: int,
    page_y: int,
) -> bool:
    rel_y = page_y - baseline
    if rel_y < model.min_y or rel_y > model.max_y:
        return True

    row = model_rows.get(rel_y)
    x0 = x
    x1 = x + model.width - 1
    observed = frozenset(px for px in ink_by_y.get(page_y, ()) if x0 <= px <= x1)

    if row is None:
        # A real horizontal gap, e.g. between the dot and stem of i, must be
        # completely blank across the glyph's own width. Ink farther right is
        # irrelevant because it belongs to later glyphs on the same text row.
        if rel_y in gap_rows:
            return not observed
        return True

    expected = frozenset(x + px for px in row)
    if not expected.issubset(observed):
        return False

    # The left edge inside this glyph box is discriminating. Extra ink to the
    # right may belong to a neighbour, but extra ink further left kills the
    # candidate immediately.
    return bool(observed) and min(observed) == min(expected)


def _full_candidate_compatible(
    ink_by_y: RowInk,
    candidate: SurvivalCandidate,
    *,
    model_rows: dict[int, frozenset[int]],
    gap_rows: frozenset[int],
) -> bool:
    return all(
        _row_compatible(
            ink_by_y,
            model=candidate.model,
            model_rows=model_rows,
            gap_rows=gap_rows,
            x=candidate.x,
            baseline=candidate.baseline,
            page_y=candidate.baseline + rel_y,
        )
        for rel_y in range(candidate.model.min_y, candidate.model.max_y + 1)
    )


def seed_candidates(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    min_y: int,
    max_y: int,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
) -> tuple[SurvivalCandidate, ...]:
    """Seed placements from real start-x pixels in the current y window."""
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return ()
    start_pixels = sorted(
        (x, y)
        for x, y in black
        if min_y <= y <= max_y and _translate_x_allowed(x, ranges)
    )
    out: dict[tuple[int, int, int], SurvivalCandidate] = {}
    for model in tuple(models):
        min_model_x = min(x for x, _y in model.pixels)
        left_rows = sorted(y for x, y in model.pixels if x == min_model_x)
        for page_x, page_y in start_pixels:
            tx = page_x - min_model_x
            if not _translate_x_allowed(tx, ranges):
                continue
            for model_y in left_rows:
                baseline = page_y - model_y
                key = (id(model), tx, baseline)
                out.setdefault(
                    key,
                    SurvivalCandidate(
                        model=model,
                        x=tx,
                        baseline=baseline,
                        seed_y=page_y,
                        survived_to_y=page_y - 1,
                    ),
                )
    return tuple(out.values())


def run_candidate_survival(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    start_y: int,
    end_y: int,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
) -> SurvivalResult:
    """Walk downward one physical raster row at a time and kill contradictions."""
    model_list = tuple(models)
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    seeded = seed_candidates(
        black,
        model_list,
        min_y=start_y,
        max_y=end_y,
        allowed_translate_x_ranges=ranges,
    )
    if not seeded:
        return SurvivalResult(completed=(), steps=(), seeded=0)

    ink_by_y = _ink_by_y(black)
    rows_by_model = {id(model): _model_rows(model) for model in model_list}
    gaps_by_model = {id(model): _internal_gap_rows(model) for model in model_list}
    live = list(seeded)
    completed: dict[tuple[int, int, int], SurvivalCandidate] = {}
    steps: list[SurvivalStep] = []

    for y in range(start_y, end_y + 1):
        before = len(live)
        next_live: list[SurvivalCandidate] = []
        for candidate in live:
            if y < candidate.seed_y:
                next_live.append(candidate)
                continue
            rows = rows_by_model[id(candidate.model)]
            gaps = gaps_by_model[id(candidate.model)]
            if not _row_compatible(
                ink_by_y,
                model=candidate.model,
                model_rows=rows,
                gap_rows=gaps,
                x=candidate.x,
                baseline=candidate.baseline,
                page_y=y,
            ):
                continue

            advanced = SurvivalCandidate(
                model=candidate.model,
                x=candidate.x,
                baseline=candidate.baseline,
                seed_y=candidate.seed_y,
                survived_to_y=y,
            )
            if y >= candidate.bottom_y:
                if _full_candidate_compatible(
                    ink_by_y,
                    advanced,
                    model_rows=rows,
                    gap_rows=gaps,
                ):
                    completed[(id(candidate.model), candidate.x, candidate.baseline)] = advanced
            else:
                next_live.append(advanced)

        live = next_live
        after = len(live)
        steps.append(SurvivalStep(y=y, before=before, after=after, died=before - after))

    ordered = tuple(
        sorted(
            completed.values(),
            key=lambda hit: (
                hit.baseline,
                hit.x,
                -len(hit.model.pixels),
                hit.model.label,
                hit.model.style,
            ),
        )
    )
    return SurvivalResult(completed=ordered, steps=tuple(steps), seeded=len(seeded))
