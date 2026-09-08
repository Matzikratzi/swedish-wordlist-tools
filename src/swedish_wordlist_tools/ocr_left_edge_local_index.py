from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


LocalRelation = tuple[int, int]
LocalSignature = tuple[LocalRelation, ...]
TranslateXRange = tuple[int, int]


@dataclass(frozen=True)
class LocalIndexedGlyph:
    model: GlyphModel
    signature: LocalSignature
    anchor_y: int
    anchor_x: int
    end_y: int


@dataclass(frozen=True)
class LocalExactHit:
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


@dataclass(frozen=True)
class PreparedLocalFingerprintIndexes:
    """Facit-derived contour fingerprints, reusable for every page/column."""

    models: tuple[GlyphModel, ...]
    min_steps: int
    max_steps: int
    max_row_gap: int
    indexes: dict[int, "LocalLeftEdgeIndex"]
    tiny: tuple[tuple[GlyphModel, LocalIndexedGlyph], ...]


def occupied_left_rows(model: GlyphModel) -> tuple[tuple[int, int], ...]:
    by_y: dict[int, int] = {}
    for x, y in model.pixels:
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(sorted(by_y.items()))


def local_relation_windows(model: GlyphModel, *, steps: int, max_row_gap: int) -> tuple[LocalIndexedGlyph, ...]:
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
        if valid:
            out.append(LocalIndexedGlyph(model, tuple(signature), window[0][0], window[0][1], window[-1][0]))
    return tuple(out)


class LocalLeftEdgeIndex:
    def __init__(self, models: Iterable[GlyphModel], *, steps: int = 4, max_row_gap: int = 1) -> None:
        self.steps = int(steps)
        self.max_row_gap = int(max_row_gap)
        self.glyphs = tuple(
            indexed
            for model in models
            for indexed in local_relation_windows(model, steps=self.steps, max_row_gap=self.max_row_gap)
        )
        buckets: dict[LocalSignature, list[LocalIndexedGlyph]] = defaultdict(list)
        for indexed in self.glyphs:
            buckets[indexed.signature].append(indexed)
        self._buckets = {key: tuple(value) for key, value in buckets.items()}

    def candidates(self, signature: LocalSignature) -> tuple[LocalIndexedGlyph, ...]:
        return self._buckets.get(tuple(signature), ())


def source_local_signatures(black: set[tuple[int, int]], *, steps: int, max_row_gap: int, min_x: int | None = None) -> tuple[tuple[int, int, LocalSignature], ...]:
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


def exact_local_model_at(black: set[tuple[int, int]], indexed: LocalIndexedGlyph, *, source_anchor_y: int, source_anchor_x: int) -> bool:
    dx = int(source_anchor_x) - indexed.anchor_x
    dy = int(source_anchor_y) - indexed.anchor_y
    return all((x + dx, y + dy) in black for x, y in indexed.model.pixels)


def derived_baseline_from_local(indexed: LocalIndexedGlyph, *, source_anchor_y: int) -> int:
    return int(source_anchor_y) - indexed.anchor_y


def _tiny_model_anchor(model: GlyphModel) -> LocalIndexedGlyph:
    rows = occupied_left_rows(model)
    y, x = rows[0]
    return LocalIndexedGlyph(model, (), y, x, y)


def _translate_x_allowed(x: int, ranges: tuple[TranslateXRange, ...] | None) -> bool:
    if ranges is None:
        return True
    return any(lo <= x <= hi for lo, hi in ranges)


def prepare_local_fingerprint_indexes(
    models: Iterable[GlyphModel], *, max_steps: int = 8, min_steps: int = 1, max_row_gap: int = 1
) -> PreparedLocalFingerprintIndexes:
    """Compute every facit-side fingerprint once for reuse across a scan."""
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if min_steps <= 0 or min_steps > max_steps:
        raise ValueError("min_steps must be in 1..max_steps")
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")
    model_rows = tuple(models)
    indexes = {
        steps: LocalLeftEdgeIndex(model_rows, steps=steps, max_row_gap=max_row_gap)
        for steps in range(min_steps, max_steps + 1)
    }
    tiny = tuple((model, _tiny_model_anchor(model)) for model in model_rows if len(occupied_left_rows(model)) == 1)
    return PreparedLocalFingerprintIndexes(model_rows, min_steps, max_steps, max_row_gap, indexes, tiny)


def ranked_exact_local_hits(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel] | None = None,
    *,
    max_steps: int = 8,
    min_steps: int = 1,
    max_row_gap: int = 1,
    max_x: int | None = None,
    include_tiny_fallback: bool = True,
    prepared: PreparedLocalFingerprintIndexes | None = None,
    scan_xs: Iterable[int] | None = None,
    allowed_translate_x_ranges: Iterable[TranslateXRange] | None = None,
) -> tuple[LocalExactHit, ...]:
    """Return exact placements; facit fingerprints may be supplied precomputed.

    ``scan_xs`` lets a caller restrict expensive source-contour resynchronisation
    to known typographic start zones instead of trying every black x coordinate.
    ``allowed_translate_x_ranges`` is the corresponding hard acceptance gate on
    the full glyph placement. Exact verification still uses every glyph pixel.
    """
    if prepared is None:
        if models is None:
            raise ValueError("models or prepared must be supplied")
        prepared = prepare_local_fingerprint_indexes(models, max_steps=max_steps, min_steps=min_steps, max_row_gap=max_row_gap)
    else:
        if (prepared.min_steps, prepared.max_steps, prepared.max_row_gap) != (min_steps, max_steps, max_row_gap):
            raise ValueError("prepared fingerprint parameters do not match search parameters")
    ranges = None if allowed_translate_x_ranges is None else tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if ranges is not None and any(lo > hi for lo, hi in ranges):
        raise ValueError("allowed translate-x ranges must have lo <= hi")
    if scan_xs is None:
        source_scan_xs = sorted({x for x, _y in black if max_x is None or x <= max_x})
    else:
        source_scan_xs = sorted({int(x) for x in scan_xs if max_x is None or int(x) <= max_x})
    hits: list[LocalExactHit] = []
    seen: set[tuple[int, int, int]] = set()
    for steps in range(max_steps, min_steps - 1, -1):
        index = prepared.indexes[steps]
        for scan_x in source_scan_xs:
            for source_y, source_x, signature in source_local_signatures(black, steps=steps, max_row_gap=max_row_gap, min_x=scan_x):
                for indexed in index.candidates(signature):
                    tx = source_x - indexed.anchor_x
                    if not _translate_x_allowed(tx, ranges):
                        continue
                    ty = source_y - indexed.anchor_y
                    placement_key = (id(indexed.model), tx, ty)
                    if placement_key in seen:
                        continue
                    if not exact_local_model_at(black, indexed, source_anchor_y=source_y, source_anchor_x=source_x):
                        continue
                    seen.add(placement_key)
                    hits.append(LocalExactHit(indexed, source_y, source_x, steps, scan_x))
    if include_tiny_fallback:
        source_points = sorted(((x, y) for x, y in black if max_x is None or x <= max_x), key=lambda point: (point[0], point[1]))
        for model, indexed in prepared.tiny:
            for source_x, source_y in source_points:
                tx = source_x - indexed.anchor_x
                if not _translate_x_allowed(tx, ranges):
                    continue
                ty = source_y - indexed.anchor_y
                placement_key = (id(model), tx, ty)
                if placement_key in seen:
                    continue
                if not exact_local_model_at(black, indexed, source_anchor_y=source_y, source_anchor_x=source_x):
                    continue
                seen.add(placement_key)
                hits.append(LocalExactHit(indexed, source_y, source_x, 0, source_x))
    hits.sort(key=lambda hit: (-hit.steps, -len(hit.model.pixels), hit.translate_x, hit.translate_y, hit.model.label, hit.model.style, hit.indexed.anchor_y))
    return tuple(hits)
