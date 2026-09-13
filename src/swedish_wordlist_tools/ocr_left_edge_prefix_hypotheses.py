from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel
from .ocr_left_edge_local_index import LocalRelation, occupied_left_rows


@dataclass(frozen=True)
class PrefixCandidate:
    model: GlyphModel
    start: int
    relations: tuple[LocalRelation, ...]


@dataclass(frozen=True)
class PrefixIndex:
    """Prefix lookup for every contiguous left-contour window in the facit.

    A source fingerprint may begin part-way through a glyph.  Every model row is
    therefore a possible anchor, and successively longer relation prefixes from
    that row are indexed.  Full raster matching is deliberately deferred until
    a candidate reaches the bottom of its own occupied y extent.
    """

    buckets: dict[tuple[LocalRelation, ...], tuple[PrefixCandidate, ...]]
    max_relations: int

    def candidates(self, relations: Iterable[LocalRelation]) -> tuple[PrefixCandidate, ...]:
        return self.buckets.get(tuple(relations), ())


def build_prefix_index(models: Iterable[GlyphModel], *, max_row_gap: int = 1) -> PrefixIndex:
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")
    mutable: dict[tuple[LocalRelation, ...], list[PrefixCandidate]] = {}
    max_relations = 0
    for model in models:
        rows = occupied_left_rows(model)
        for start in range(len(rows) - 1):
            relations: list[LocalRelation] = []
            for pos in range(start, len(rows) - 1):
                y0, x0 = rows[pos]
                y1, x1 = rows[pos + 1]
                dy = y1 - y0
                if dy > max_row_gap:
                    break
                relations.append((dy, x1 - x0))
                key = tuple(relations)
                mutable.setdefault(key, []).append(PrefixCandidate(model, start, key))
                max_relations = max(max_relations, len(key))
    return PrefixIndex({key: tuple(value) for key, value in mutable.items()}, max_relations)


@dataclass(frozen=True)
class MatureCandidateTest:
    """A candidate whose complete remaining vertical contour has been observed."""

    model: GlyphModel
    model_start_row: int
    source_start_row: int
    source_end_row: int
    relations: tuple[LocalRelation, ...]
    translate_x: int
    baseline: int
    exact: bool


@dataclass(frozen=True)
class PrefixRun:
    """One active fingerprint between impossible extensions/resets."""

    source_start_row: int
    source_end_row: int
    relations: tuple[LocalRelation, ...]
    surviving_candidates: int
    mature_tests: tuple[MatureCandidateTest, ...]


def _candidate_is_vertically_complete(candidate: PrefixCandidate, relation_count: int) -> bool:
    rows = occupied_left_rows(candidate.model)
    return candidate.start + relation_count == len(rows) - 1


def _exact_candidate_at_source(
    black: set[tuple[int, int]],
    source_rows: tuple[tuple[int, int], ...],
    *,
    source_start_row: int,
    candidate: PrefixCandidate,
) -> tuple[int, int, bool]:
    model_rows = occupied_left_rows(candidate.model)
    source_y, source_x = source_rows[source_start_row]
    model_y, model_x = model_rows[candidate.start]
    tx = source_x - model_x
    baseline = source_y - model_y
    exact = all((x + tx, y + baseline) in black for x, y in candidate.model.pixels)
    return tx, baseline, exact


def scan_prefix_candidate_lifetimes(
    rows: Iterable[tuple[int, int]],
    *,
    black: set[tuple[int, int]],
    index: PrefixIndex,
    max_row_gap: int = 1,
) -> tuple[PrefixRun, ...]:
    """Grow one fingerprint and raster-test each candidate at its own y end.

    There is no reason to keep an impossible old fingerprint alive.  When an
    extension has zero facit candidates, the current run ends and the offending
    relation is tried as the beginning of a fresh run.  Candidates are *not*
    raster-tested merely because few remain: each one is tested exactly when
    the observed source fingerprint reaches the last occupied left-contour row
    available to that candidate.  The full model raster is then checked against
    the original source pixels, including any rows above the fingerprint anchor.
    """
    source = tuple(rows)
    if len(source) < 2:
        return ()
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")

    runs: list[PrefixRun] = []
    run_start = 0
    relations: list[LocalRelation] = []
    tested_placements: set[tuple[int, int, int]] = set()
    mature_tests: list[MatureCandidateTest] = []
    surviving = 0

    def finish(end_row: int) -> None:
        nonlocal relations, mature_tests, surviving, run_start
        if relations:
            runs.append(
                PrefixRun(
                    source_start_row=run_start,
                    source_end_row=end_row,
                    relations=tuple(relations),
                    surviving_candidates=surviving,
                    mature_tests=tuple(mature_tests),
                )
            )
        relations = []
        mature_tests = []
        surviving = 0

    def accept_relation(relation: LocalRelation, *, source_end_row: int) -> bool:
        nonlocal relations, mature_tests, surviving
        proposed = tuple(relations + [relation])
        candidates = index.candidates(proposed)
        if not candidates:
            return False
        relations.append(relation)
        surviving = len(candidates)
        for candidate in candidates:
            if not _candidate_is_vertically_complete(candidate, len(relations)):
                continue
            tx, baseline, exact = _exact_candidate_at_source(
                black,
                source,
                source_start_row=run_start,
                candidate=candidate,
            )
            placement = (id(candidate.model), tx, baseline)
            if placement in tested_placements:
                continue
            tested_placements.add(placement)
            mature_tests.append(
                MatureCandidateTest(
                    model=candidate.model,
                    model_start_row=candidate.start,
                    source_start_row=run_start,
                    source_end_row=source_end_row,
                    relations=tuple(relations),
                    translate_x=tx,
                    baseline=baseline,
                    exact=exact,
                )
            )
        return True

    for pos, ((y0, x0), (y1, x1)) in enumerate(zip(source, source[1:])):
        relation = (y1 - y0, x1 - x0)
        if relation[0] > max_row_gap:
            finish(pos)
            run_start = pos + 1
            continue

        if accept_relation(relation, source_end_row=pos + 1):
            continue

        # The old fingerprint plus this relation is impossible.  Drop it: only
        # the boundary matters.  Try the offending relation as a clean start.
        finish(pos)
        run_start = pos
        if not accept_relation(relation, source_end_row=pos + 1):
            relations = []
            mature_tests = []
            surviving = 0
            run_start = pos + 1

    finish(len(source) - 1)
    return tuple(runs)
