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

    A source hypothesis may begin part-way through a glyph.  Therefore every
    model row is a possible start, and every successively longer relation prefix
    from that row is indexed.  This lets a row walker ask cheaply whether a
    partial contour can still belong to any known glyph before doing raster
    verification.
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
class SourceTrack:
    start_row: int
    end_row: int
    relations: tuple[LocalRelation, ...]
    candidate_count: int


@dataclass(frozen=True)
class BranchEvent:
    failed: SourceTrack
    restarted: SourceTrack | None


def branch_source_left_contour(
    rows: Iterable[tuple[int, int]],
    *,
    index: PrefixIndex,
    max_row_gap: int = 1,
) -> tuple[SourceTrack, ...]:
    """Split a source left contour whenever the current fingerprint becomes impossible.

    The completed track is retained.  A fresh hypothesis is then started from
    the relation that made the previous one impossible; if that relation is
    itself impossible, the next relation gets a clean start.  The result is a
    small sequence of contour fragments rather than an eager pixel-level glyph
    segmentation.
    """
    source = tuple(rows)
    if len(source) < 2:
        return ()
    tracks: list[SourceTrack] = []
    current_start = 0
    current: list[LocalRelation] = []
    last_candidate_count = 0

    def finish(end_row: int) -> None:
        nonlocal current, last_candidate_count, current_start
        if current:
            tracks.append(SourceTrack(current_start, end_row, tuple(current), last_candidate_count))
        current = []
        last_candidate_count = 0

    for pos, ((y0, x0), (y1, x1)) in enumerate(zip(source, source[1:])):
        relation = (y1 - y0, x1 - x0)
        if relation[0] > max_row_gap:
            finish(pos)
            current_start = pos + 1
            continue

        proposed = tuple(current + [relation])
        candidates = index.candidates(proposed)
        if candidates:
            current.append(relation)
            last_candidate_count = len(candidates)
            continue

        # The new relation cannot extend the old hypothesis.  Preserve the old
        # fingerprint and try the offending relation as the start of a new one.
        finish(pos)
        current_start = pos
        single = (relation,)
        candidates = index.candidates(single)
        if candidates:
            current = [relation]
            last_candidate_count = len(candidates)
        else:
            current_start = pos + 1

    finish(len(source) - 1)
    return tuple(tracks)
