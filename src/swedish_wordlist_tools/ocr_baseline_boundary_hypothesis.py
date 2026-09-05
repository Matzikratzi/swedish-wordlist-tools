from __future__ import annotations

"""Experimental baseline-first evidence for an OCR row's lower boundary.

The experiment deliberately does not move ownership.  It asks a narrower
question: given a trusted baseline, can a glyph be recognised from pixels on or
above that baseline, survive a short probe below it, and then be followed to its
full learned lower extent?  Such a glyph proves that the current row extends at
least that far down.
"""

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel


@dataclass(frozen=True)
class DescenderProof:
    label: str
    style: str
    x: int
    baseline: int
    probe_bottom: int
    proven_bottom: int


@dataclass(frozen=True)
class BaselineBoundaryHypothesis:
    baseline: int
    upper_candidates: int
    probe_candidates: int
    proofs: tuple[DescenderProof, ...]
    proven_bottom: int | None
    boundary: int | None


def _placed(points, *, x0: int, baseline: int) -> frozenset[tuple[int, int]]:
    return frozenset((x0 + int(x), baseline + int(y)) for x, y in points)


def baseline_boundary_hypothesis(
    ink: set[tuple[int, int]],
    *,
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    baseline: int,
    probe_depth: int = 3,
) -> BaselineBoundaryHypothesis:
    """Return lower-boundary evidence without using lower ink to find a glyph.

    Candidate discovery uses only model/source pixels at ``y <= baseline``.
    A discovered candidate is then allowed to inspect at most ``probe_depth``
    raster lines below the baseline.  Only if all learned pixels in that probe
    are present do we follow the same glyph to its complete learned lower
    extent.  Unexpected black pixels are ignored: they may belong to an
    adjacent glyph, so they are not evidence either for or against this glyph.

    ``boundary`` is one raster line below the lowest proven glyph pixel.  It is
    a hypothesis only; callers must not alter row ownership from this value
    without an independent adjacent-row proof.
    """
    if probe_depth < 1:
        raise ValueError("probe_depth must be >= 1")
    if not 0 <= int(baseline) < int(height):
        raise ValueError("baseline outside raster")

    source = frozenset((int(x), int(y)) for x, y in ink)
    upper_source = frozenset((x, y) for x, y in source if y <= baseline)
    upper_candidates = 0
    probe_candidates = 0
    proofs: list[DescenderProof] = []

    for model in models:
        upper_model = tuple((x, y) for x, y in model.pixels if y <= 0)
        lower_model = tuple((x, y) for x, y in model.pixels if y > 0)
        if not upper_model or not lower_model:
            continue

        probe_model = tuple((x, y) for x, y in lower_model if y <= probe_depth)
        if not probe_model:
            # The experiment intentionally requires nearby evidence before it
            # follows a glyph farther down.
            continue

        model_min_x = min(x for x, _y in model.pixels)
        model_max_x = max(x for x, _y in model.pixels)
        x0_lo = -model_min_x
        x0_hi = width - 1 - model_max_x
        if x0_hi < x0_lo:
            continue

        for x0 in range(x0_lo, x0_hi + 1):
            placed_upper = _placed(upper_model, x0=x0, baseline=baseline)
            if not placed_upper.issubset(upper_source):
                continue
            upper_candidates += 1

            placed_probe = _placed(probe_model, x0=x0, baseline=baseline)
            if any(y >= height for _x, y in placed_probe) or not placed_probe.issubset(source):
                continue
            probe_candidates += 1

            placed_lower = _placed(lower_model, x0=x0, baseline=baseline)
            if any(y >= height for _x, y in placed_lower) or not placed_lower.issubset(source):
                continue

            probe_bottom = max(y for _x, y in placed_probe)
            proven_bottom = max(y for _x, y in placed_lower)
            proofs.append(
                DescenderProof(
                    label=model.label,
                    style=model.style,
                    x=x0,
                    baseline=baseline,
                    probe_bottom=probe_bottom,
                    proven_bottom=proven_bottom,
                )
            )

    # The same raster may exist in several facit entries.  Keep one proof per
    # visible placement so diagnostics are stable and compact.
    unique: dict[tuple[str, int, int], DescenderProof] = {}
    for proof in proofs:
        key = (proof.label, proof.x, proof.proven_bottom)
        current = unique.get(key)
        if current is None or (proof.style, proof.probe_bottom) < (current.style, current.probe_bottom):
            unique[key] = proof
    ordered = tuple(sorted(unique.values(), key=lambda p: (p.x, p.proven_bottom, p.label, p.style)))
    bottom = max((proof.proven_bottom for proof in ordered), default=None)
    return BaselineBoundaryHypothesis(
        baseline=int(baseline),
        upper_candidates=upper_candidates,
        probe_candidates=probe_candidates,
        proofs=ordered,
        proven_bottom=bottom,
        boundary=None if bottom is None else bottom + 1,
    )
