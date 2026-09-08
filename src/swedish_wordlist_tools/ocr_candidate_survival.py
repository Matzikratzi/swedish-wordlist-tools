from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


TranslateXRange = tuple[int, int]


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
    born: int
    before: int
    after: int
    died: int
    completed: int


@dataclass(frozen=True)
class SurvivalResult:
    completed: tuple[SurvivalCandidate, ...]
    steps: tuple[SurvivalStep, ...]
    seeded: int


def _translate_x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def _model_rows(model: GlyphModel) -> dict[int, frozenset[int]]:
    by_y: dict[int, set[int]] = {}
    for x, y in model.pixels:
        by_y.setdefault(y, set()).add(x)
    return {y: frozenset(xs) for y, xs in by_y.items()}


def _internal_gap_rows(model: GlyphModel) -> frozenset[int]:
    occupied = {y for _x, y in model.pixels}
    return frozenset(y for y in range(model.min_y + 1, model.max_y) if y not in occupied)


def _black_by_y(black: set[tuple[int, int]]) -> dict[int, tuple[int, ...]]:
    by_y: dict[int, list[int]] = defaultdict(list)
    for x, y in black:
        by_y[y].append(x)
    return {y: tuple(sorted(xs)) for y, xs in by_y.items()}


def _row_compatible(
    black_by_y: dict[int, tuple[int, ...]],
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
    observed = tuple(px for px in black_by_y.get(page_y, ()) if x0 <= px <= x1)

    if row is None:
        if rel_y in gap_rows:
            return not observed
        return True

    expected = {x + px for px in row}
    observed_set = set(observed)
    if not expected.issubset(observed_set):
        return False

    # Extra ink to the right can belong to a neighbouring glyph. Ink to the
    # left of the model's own left edge on this raster row contradicts the
    # candidate immediately.
    return bool(observed) and observed[0] == min(expected)


def _full_candidate_compatible(
    black_by_y: dict[int, tuple[int, ...]],
    candidate: SurvivalCandidate,
    *,
    model_rows: dict[int, frozenset[int]],
    gap_rows: frozenset[int],
) -> bool:
    return all(
        _row_compatible(
            black_by_y,
            model=candidate.model,
            model_rows=model_rows,
            gap_rows=gap_rows,
            x=candidate.x,
            baseline=candidate.baseline,
            page_y=candidate.baseline + rel_y,
        )
        for rel_y in range(candidate.model.min_y, candidate.model.max_y + 1)
    )


def _has_ink_in_span(
    black_by_y: dict[int, tuple[int, ...]],
    *,
    y: int,
    x0: int,
    x1: int,
) -> bool:
    return any(x0 <= px <= x1 for px in black_by_y.get(y, ()))


def _seed_at_y(
    black_by_y: dict[int, tuple[int, ...]],
    models: tuple[GlyphModel, ...],
    *,
    y: int,
    ranges: tuple[TranslateXRange, ...],
    rows_by_model: dict[int, dict[int, frozenset[int]]],
    gaps_by_model: dict[int, frozenset[int]],
) -> tuple[SurvivalCandidate, ...]:
    """Create hypotheses whose physical raster top starts at ``y``.

    A candidate is born only at a real new top: its top glyph row must match at
    ``y`` and the same horizontal glyph span must be blank at ``y - 1``.  Thus a
    vertical stroke continuing straight down advances an existing candidate
    instead of spawning the same model again one pixel lower.
    """
    page_xs = black_by_y.get(y, ())
    if not page_xs:
        return ()

    out: dict[tuple[int, int, int], SurvivalCandidate] = {}
    for model in models:
        top_row = rows_by_model[id(model)].get(model.min_y)
        if not top_row:
            continue
        top_left = min(top_row)
        for page_x in page_xs:
            tx = page_x - top_left
            if not _translate_x_allowed(tx, ranges):
                continue
            baseline = y - model.min_y
            if not _row_compatible(
                black_by_y,
                model=model,
                model_rows=rows_by_model[id(model)],
                gap_rows=gaps_by_model[id(model)],
                x=tx,
                baseline=baseline,
                page_y=y,
            ):
                continue
            if _has_ink_in_span(
                black_by_y,
                y=y - 1,
                x0=tx,
                x1=tx + model.width - 1,
            ):
                continue
            key = (id(model), tx, baseline)
            out[key] = SurvivalCandidate(
                model=model,
                x=tx,
                baseline=baseline,
                seed_y=y,
                survived_to_y=y,
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
    """Walk down one raster row at a time; candidates are born and die online."""
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")

    model_list = tuple(models)
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return SurvivalResult(completed=(), steps=(), seeded=0)

    page_rows = _black_by_y(black)
    rows_by_model = {id(model): _model_rows(model) for model in model_list}
    gaps_by_model = {id(model): _internal_gap_rows(model) for model in model_list}

    live: dict[tuple[int, int, int], SurvivalCandidate] = {}
    completed: dict[tuple[int, int, int], SurvivalCandidate] = {}
    steps: list[SurvivalStep] = []
    seeded_total = 0

    for y in range(start_y, end_y + 1):
        born_candidates = _seed_at_y(
            page_rows,
            model_list,
            y=y,
            ranges=ranges,
            rows_by_model=rows_by_model,
            gaps_by_model=gaps_by_model,
        )
        born = 0
        for candidate in born_candidates:
            key = (id(candidate.model), candidate.x, candidate.baseline)
            if key not in live and key not in completed:
                live[key] = candidate
                born += 1
        seeded_total += born

        before = len(live)
        next_live: dict[tuple[int, int, int], SurvivalCandidate] = {}
        completed_now = 0
        for key, candidate in live.items():
            rows = rows_by_model[id(candidate.model)]
            gaps = gaps_by_model[id(candidate.model)]
            if y > candidate.seed_y and not _row_compatible(
                page_rows,
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
                    page_rows,
                    advanced,
                    model_rows=rows,
                    gap_rows=gaps,
                ):
                    completed[key] = advanced
                    completed_now += 1
            else:
                next_live[key] = advanced

        live = next_live
        after = len(live)
        died = before - after - completed_now
        steps.append(
            SurvivalStep(
                y=y,
                born=born,
                before=before,
                after=after,
                died=max(0, died),
                completed=completed_now,
            )
        )

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
    return SurvivalResult(completed=ordered, steps=tuple(steps), seeded=seeded_total)
