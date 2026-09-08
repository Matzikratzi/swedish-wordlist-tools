from __future__ import annotations

from typing import Iterable

from .ocr_glyph_matcher import GlyphModel
from .ocr_left_edge_prefix_hypotheses import build_prefix_index, scan_prefix_candidate_lifetimes
from .ocr_row_finder_one_at_a_time import FoundRowStart


TranslateXRange = tuple[int, int]


def _left_rows(black: set[tuple[int, int]], *, min_x: int) -> tuple[tuple[int, int], ...]:
    by_y: dict[int, int] = {}
    for x, y in black:
        if x < min_x:
            continue
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(sorted(by_y.items()))


def _allowed_x(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def exact_mature_prefix_row_starts(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    start_ranges: Iterable[TranslateXRange],
    max_row_gap: int = 1,
) -> tuple[FoundRowStart, ...]:
    """Find exact row-start glyphs that mature through prefix fingerprinting.

    This is a fallback for starts such as ``~e`` where a very shallow leading
    glyph can mask the ordinary longer left-edge fingerprint.  Candidate
    contours are grown until each model reaches its own final occupied y row;
    only then is the complete model raster tested.  No punctuation labels are
    special-cased.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in start_ranges)
    if not ranges:
        return ()
    if any(lo > hi for lo, hi in ranges):
        raise ValueError("start ranges must have lo <= hi")
    model_rows = tuple(models)
    index = build_prefix_index(model_rows, max_row_gap=max_row_gap)

    thresholds = sorted({x for lo, hi in ranges for x in range(lo, hi + 1)})
    previous_rows: tuple[tuple[int, int], ...] | None = None
    out: list[FoundRowStart] = []
    seen: set[tuple[int, int, int]] = set()
    for threshold_x in thresholds:
        rows = _left_rows(black, min_x=threshold_x)
        if rows == previous_rows:
            continue
        previous_rows = rows
        if len(rows) < 2:
            continue
        runs = scan_prefix_candidate_lifetimes(
            rows,
            black=black,
            index=index,
            max_row_gap=max_row_gap,
        )
        for run in runs:
            for test in run.mature_tests:
                if not test.exact or not _allowed_x(test.translate_x, ranges):
                    continue
                key = (id(test.model), test.translate_x, test.baseline)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    FoundRowStart(
                        x=test.translate_x,
                        top_y=test.baseline + test.model.min_y,
                        bottom_y=test.baseline + test.model.max_y,
                        baseline=test.baseline,
                        label=test.model.label,
                        style=test.model.style,
                        steps=len(test.relations),
                    )
                )
    out.sort(key=lambda start: (start.top_y, start.x, -start.steps, start.label, start.style))
    return tuple(out)
