from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


LocalRelation = tuple[int, int]  # (dy, dx)
LocalSignature = tuple[LocalRelation, ...]


@dataclass(frozen=True)
class LocalIndexedGlyph:
    """One local left-contour window inside a glyph model.

    ``anchor_y``/``anchor_x`` identify the first occupied model row in the
    window.  A source hit therefore determines the full glyph translation even
    when the matched contour window begins in the middle of the glyph.
    """

    model: GlyphModel
    signature: LocalSignature
    anchor_y: int
    anchor_x: int
    end_y: int


@dataclass(frozen=True)
class LocalExactHit:
    """One exact glyph placement implied by a local contour fingerprint."""

    indexed: LocalIndexedGlyph
    source_anchor_y: int
    source_anchor_x: int
    steps: int
    scan_x: int

    @property
    def model(self) -> GlyphModel:
        return self.indexed.model

    @property
    def translate_x(self) -> int:
        return self.source_anchor_x - self.indexed.anchor_x

    @property
    def translate_y(self) -> int:
        return self.source_anchor_y - self.indexed.anchor_y

    @property
    def baseline(self) -> int:
        return self.translate_y


def occupied_left_rows(model: GlyphModel) -> tuple[tuple[int, int], ...]:
    """Return ``(y, leftmost_x)`` for every occupied raster row in a glyph."""
    by_y: dict[int, int] = {}
    for x, y in model.pixels:
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(sorted(by_y.items()))


def local_relation_windows(
    model: GlyphModel,
    *,
    steps: int,
    max_row_gap: int,
) -> tuple[LocalIndexedGlyph, ...]:
    """Build local ``(dy, dx)`` contour windows anywhere in a glyph.

    Only neighbouring occupied rows whose vertical separation is at most
    ``max_row_gap`` may contribute a relation.  A larger gap therefore breaks a
    window instead of producing a meaningless large ``dx`` across an all-white
    raster run.
    """
    if steps <= 0:
        raise ValueError("steps must be positive")
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")

    rows = occupied_left_rows(model)
    if len(rows) < steps + 1:
        return ()

    out: list[LocalIndexedGlyph] = []
    for start in range(len(rows) - steps):
        window = rows[start : start + steps + 1]
        signature: list[LocalRelation] = []
        valid = True
        for (y0, x0), (y1, x1) in zip(window, window[1:]):
            dy = y1 - y0
            if dy > max_row_gap:
                valid = False
                break
            signature.append((dy, x1 - x0))
        if not valid:
            continue
        out.append(
            LocalIndexedGlyph(
                model=model,
                signature=tuple(signature),
                anchor_y=window[0][0],
                anchor_x=window[0][1],
                end_y=window[-1][0],
            )
        )
    return tuple(out)


class LocalLeftEdgeIndex:
    """Index short left-contour relations from any vertical glyph position.

    This is deliberately a candidate generator, not a recognizer.  A hit must
    still be followed by complete exact raster verification of the glyph.
    """

    def __init__(
        self,
        models: Iterable[GlyphModel],
        *,
        steps: int = 4,
        max_row_gap: int = 1,
    ) -> None:
        self.steps = int(steps)
        self.max_row_gap = int(max_row_gap)
        glyphs = [
            indexed
            for model in models
            for indexed in local_relation_windows(
                model,
                steps=self.steps,
                max_row_gap=self.max_row_gap,
            )
        ]
        self.glyphs = tuple(glyphs)
        buckets: dict[LocalSignature, list[LocalIndexedGlyph]] = defaultdict(list)
        for indexed in self.glyphs:
            buckets[indexed.signature].append(indexed)
        self._buckets = {key: tuple(value) for key, value in buckets.items()}

    def candidates(self, signature: LocalSignature) -> tuple[LocalIndexedGlyph, ...]:
        return self._buckets.get(tuple(signature), ())


def source_local_signatures(
    black: set[tuple[int, int]],
    *,
    steps: int,
    max_row_gap: int,
    min_x: int | None = None,
) -> tuple[tuple[int, int, LocalSignature], ...]:
    """Read all local left-contour windows from source ink.

    Returns ``(anchor_y, anchor_x, signature)``.  Like the model index, gaps
    larger than ``max_row_gap`` break windows rather than creating a cross-gap
    ``dx`` relation.  ``min_x`` permits cheap horizontal resynchronisation: on
    each raster row only ink at or to the right of that x may define the local
    left contour.
    """
    if steps <= 0:
        raise ValueError("steps must be positive")
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")

    by_y: dict[int, int] = {}
    for x, y in black:
        if min_x is not None and x < min_x:
            continue
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    rows = tuple(sorted(by_y.items()))
    if len(rows) < steps + 1:
        return ()

    out: list[tuple[int, int, LocalSignature]] = []
    for start in range(len(rows) - steps):
        window = rows[start : start + steps + 1]
        signature: list[LocalRelation] = []
        valid = True
        for (y0, x0), (y1, x1) in zip(window, window[1:]):
            dy = y1 - y0
            if dy > max_row_gap:
                valid = False
                break
            signature.append((dy, x1 - x0))
        if valid:
            out.append((window[0][0], window[0][1], tuple(signature)))
    return tuple(out)


def exact_local_model_at(
    black: set[tuple[int, int]],
    indexed: LocalIndexedGlyph,
    *,
    source_anchor_y: int,
    source_anchor_x: int,
) -> bool:
    """Verify the complete glyph raster from a local contour hit."""
    dx = int(source_anchor_x) - indexed.anchor_x
    dy = int(source_anchor_y) - indexed.anchor_y
    return all((x + dx, y + dy) in black for x, y in indexed.model.pixels)


def derived_baseline_from_local(
    indexed: LocalIndexedGlyph,
    *,
    source_anchor_y: int,
) -> int:
    """Derive the model baseline from a local contour hit."""
    return int(source_anchor_y) - indexed.anchor_y


def _tiny_model_anchor(model: GlyphModel) -> LocalIndexedGlyph:
    rows = occupied_left_rows(model)
    y, x = rows[0]
    return LocalIndexedGlyph(
        model=model,
        signature=(),
        anchor_y=y,
        anchor_x=x,
        end_y=y,
    )


def ranked_exact_local_hits(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    max_steps: int = 8,
    min_steps: int = 1,
    max_row_gap: int = 1,
    max_x: int | None = None,
    include_tiny_fallback: bool = True,
) -> tuple[LocalExactHit, ...]:
    """Return exact local-contour placements, longest fingerprints first.

    The source contour is cheap to recompute for each distinct possible
    horizontal resynchronisation x.  Each fingerprint bucket already contains
    a model-local anchor, so a bucket hit implies one concrete glyph placement;
    there is no x/y sliding during exact verification.

    Long windows are tried before short ones.  Tiny glyphs with fewer than two
    occupied rows cannot contribute even one dx relation; when requested they
    are tested only after all real fingerprint hits, by aligning their first
    left contour pixel with source ink.  Thus punctuation cannot win merely
    because empty raster around it happens to fit.
    """
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if min_steps <= 0 or min_steps > max_steps:
        raise ValueError("min_steps must be in 1..max_steps")
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")
    model_rows = tuple(models)
    scan_xs = sorted({x for x, _y in black if max_x is None or x <= max_x})
    indexes = {
        steps: LocalLeftEdgeIndex(model_rows, steps=steps, max_row_gap=max_row_gap)
        for steps in range(min_steps, max_steps + 1)
    }

    hits: list[LocalExactHit] = []
    seen: set[tuple[int, int, int]] = set()
    for steps in range(max_steps, min_steps - 1, -1):
        index = indexes[steps]
        for scan_x in scan_xs:
            for source_y, source_x, signature in source_local_signatures(
                black,
                steps=steps,
                max_row_gap=max_row_gap,
                min_x=scan_x,
            ):
                for indexed in index.candidates(signature):
                    tx = source_x - indexed.anchor_x
                    ty = source_y - indexed.anchor_y
                    placement_key = (id(indexed.model), tx, ty)
                    if placement_key in seen:
                        continue
                    if not exact_local_model_at(
                        black,
                        indexed,
                        source_anchor_y=source_y,
                        source_anchor_x=source_x,
                    ):
                        continue
                    seen.add(placement_key)
                    hits.append(
                        LocalExactHit(
                            indexed=indexed,
                            source_anchor_y=source_y,
                            source_anchor_x=source_x,
                            steps=steps,
                            scan_x=scan_x,
                        )
                    )

    if include_tiny_fallback:
        tiny_models = [model for model in model_rows if len(occupied_left_rows(model)) == 1]
        source_points = sorted(
            ((x, y) for x, y in black if max_x is None or x <= max_x),
            key=lambda point: (point[0], point[1]),
        )
        for model in tiny_models:
            indexed = _tiny_model_anchor(model)
            for source_x, source_y in source_points:
                tx = source_x - indexed.anchor_x
                ty = source_y - indexed.anchor_y
                placement_key = (id(model), tx, ty)
                if placement_key in seen:
                    continue
                if not exact_local_model_at(
                    black,
                    indexed,
                    source_anchor_y=source_y,
                    source_anchor_x=source_x,
                ):
                    continue
                seen.add(placement_key)
                hits.append(
                    LocalExactHit(
                        indexed=indexed,
                        source_anchor_y=source_y,
                        source_anchor_x=source_x,
                        steps=0,
                        scan_x=source_x,
                    )
                )

    hits.sort(
        key=lambda hit: (
            -hit.steps,
            -len(hit.model.pixels),
            hit.translate_x,
            hit.translate_y,
            hit.model.label,
            hit.model.style,
            hit.indexed.anchor_y,
        )
    )
    return tuple(hits)
