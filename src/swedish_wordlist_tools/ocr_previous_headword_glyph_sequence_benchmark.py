from __future__ import annotations

"""Benchmark result-neutral reuse of the previous exact headword glyph sequence.

For a new headword row, try the exact glyph-model sequence from the previous
headword first. If the expected glyph does not fit, try full/half boundary marks
(`|` and `·`) without consuming the previous-sequence position. Only after that
fall back to the ordinary candidate order. Candidate ordering differs, but the
shared exact-cover admissibility rules are the same as in the editor.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from . import ocr_context_anchor_benchmark as context_anchor
from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_single_downshift_safe_islands_benchmark as downstream
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit

_BREAKS = {"|", "·"}
_STATS: Counter[str] = Counter()


def _raster(model: GlyphModel):
    return tuple(sorted((int(x), int(y)) for x, y in model.pixels))


def _model_signature(model: GlyphModel):
    return (str(model.label), str(model.style), _raster(model))


def _match_raster(match: Match):
    x0 = int(getattr(match, "x", 0))
    baseline = int(getattr(match, "baseline", 0))
    return tuple(
        sorted(
            (int(x) - x0, int(y) - baseline)
            for x, y in getattr(match, "pixels", ())
        )
    )


def _match_signature(match: Match):
    return (str(match.label), str(match.style), _match_raster(match))


def _same_expected_model(model: GlyphModel, expected) -> bool:
    if expected is None:
        return False
    label, style, raster = expected
    return str(model.label) == label and str(model.style) == style and _raster(model) == raster


def _ordered_rows(rows, expected):
    """Stable tiers: exact previous glyph, boundary marks, then old order."""
    exact = []
    breaks = []
    rest = []
    for row in rows:
        model = row[0]
        if _same_expected_model(model, expected):
            exact.append(row)
        elif str(model.label) in _BREAKS:
            breaks.append(row)
        else:
            rest.append(row)
    if exact:
        _STATS["expected_promotions"] += len(exact)
    _STATS["sequence_states"] += 1
    yield from exact
    yield from breaks
    yield from rest


def _sequence_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
):
    if not ink:
        return None

    page_candidates = cached._bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    previous_sequence = getattr(priority._tls, "previous_headword_glyph_sequence", None)
    if row_kind not in {"headword", "homonym"}:
        previous_sequence = None
    if previous_sequence:
        _STATS["calls_with_previous"] += 1

    target = frozenset(ink)
    failed: set[
        tuple[frozenset[tuple[int, int]], int | None, bool, int, bool, int | None]
    ] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
        seq_index: int,
        sequence_active: bool,
        previous_right: int | None,
    ):
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (
            remaining,
            baseline,
            leading_homonym_seen,
            seq_index,
            sequence_active,
            previous_right,
        )
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        expected = None
        if sequence_active and previous_sequence and seq_index < len(previous_sequence):
            expected = previous_sequence[seq_index]

        base_rows = cached._iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        )
        rows = base_rows if expected is None else _ordered_rows(base_rows, expected)

        for model, min_x, left_pixels in rows:
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                is_leading_homonym = (
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
                )
                if baseline is not None and candidate_baseline != baseline:
                    continue
                if candidate_baseline < -model.min_y or candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                fits = True
                for x, y in model.pixels:
                    if (x0 + x, candidate_baseline + y) not in remaining:
                        fits = False
                        break
                if not fits:
                    continue
                placed = frozenset((x0 + x, candidate_baseline + y) for x, y in model.pixels)
                if not cached.placement_advances_right(placed, previous_right):
                    continue

                match = Match(
                    label=model.label,
                    style=model.style,
                    x=x0,
                    baseline=candidate_baseline,
                    pixels=placed,
                    model_pixels=len(model.pixels),
                    sources=model.sources,
                )
                if is_leading_homonym:
                    next_baseline = None
                    saw_homonym = True
                    next_index = seq_index
                    next_active = sequence_active
                else:
                    next_baseline = candidate_baseline if baseline is None else baseline
                    saw_homonym = leading_homonym_seen
                    typography = priority._typographic_style(model.style)
                    if sequence_active and typography == "bold":
                        if expected is not None and _same_expected_model(model, expected):
                            next_index = seq_index + 1
                            next_active = True
                            _STATS["expected_fits"] += 1
                        elif str(model.label) in _BREAKS:
                            next_index = seq_index
                            next_active = True
                            _STATS["break_fits"] += 1
                        else:
                            next_index = seq_index
                            next_active = False
                            _STATS["sequence_diverged"] += 1
                    elif sequence_active and str(model.label) in _BREAKS:
                        next_index = seq_index
                        next_active = True
                        _STATS["break_fits"] += 1
                    else:
                        next_index = seq_index
                        next_active = False

                tail = search(
                    frozenset(remaining.difference(placed)),
                    next_baseline,
                    priority._typographic_style(model.style),
                    saw_homonym,
                    next_index,
                    next_active,
                    cached._placed_right(placed),
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, None, False, 0, bool(previous_sequence), None)
    _STATS["calls"] += 1
    _STATS["states"] += states
    _STATS["placements"] += placements_tested
    if chosen is None:
        return None
    selected = sorted(chosen, key=lambda m: (m.x, m.baseline, m.label, str(m.style)))
    if row_kind == "homonym" and selected and priority._is_homonym_match(selected[0]):
        normal = next((m for m in selected[1:] if not priority._is_homonym_match(m)), None)
        baseline_out = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline_out = selected[0].baseline
    return baseline_out, selected, placements_tested


def _sequence_fixed_baseline_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    fixed_baseline: int,
    *,
    max_states: int = 20000,
):
    return _ORIGINAL_FIXED(
        ink,
        width,
        height,
        models,
        fixed_baseline,
        max_states=max_states,
    )


@dataclass
class _Tracker:
    previous_sequence: tuple | None = None
    active_key: tuple[int, int, int] | None = None
    previous_for_active: tuple | None = None
    exact_sequence_for_active: tuple | None = None


_TRACKER = _Tracker()
_ORIGINAL_LOAD = page_editor._load_owned_row_state


def _extract_headword_sequence(state: dict, models: Iterable[GlyphModel]):
    matches = list(state.get("matches") or state.get("selected") or [])
    matches.sort(key=lambda m: (int(getattr(m, "x", 0)), int(getattr(m, "baseline", 0))))
    model_rows = list(models)
    sequence = []
    started = False
    for match in matches:
        if priority._is_homonym_match(match) and not started:
            continue
        label = str(getattr(match, "label", ""))
        style = str(getattr(match, "style", ""))
        typography = priority._typographic_style(style)
        if typography == "bold" or (started and label in _BREAKS):
            started = True
            match_signature = _match_signature(match)
            candidates = [
                model for model in model_rows
                if _model_signature(model) == match_signature
            ]
            if not candidates:
                return None
            candidates.sort(key=priority._canonical_model_key)
            sequence.append(_model_signature(candidates[0]))
            continue
        if started:
            break
    return tuple(sequence) if sequence else None


def _looks_like_headword(state: dict) -> bool:
    matches = list(state.get("matches") or state.get("selected") or [])
    matches.sort(key=lambda m: (int(getattr(m, "x", 0)), int(getattr(m, "baseline", 0))))
    if not matches:
        return False
    index = 0
    if priority._is_homonym_match(matches[0]):
        index = 1
    return index < len(matches) and priority._typographic_style(getattr(matches[index], "style", "")) == "bold"


def _tracked_load(context: dict, position: tuple[int, int], models):
    page = int(context.get("page_number", -1))
    key = (page, int(position[0]), int(position[1]))
    if key != _TRACKER.active_key:
        if _TRACKER.exact_sequence_for_active:
            _TRACKER.previous_sequence = _TRACKER.exact_sequence_for_active
            _STATS["committed_headwords"] += 1
        _TRACKER.active_key = key
        _TRACKER.previous_for_active = _TRACKER.previous_sequence
        _TRACKER.exact_sequence_for_active = None

    priority._tls.previous_headword_glyph_sequence = _TRACKER.previous_for_active
    state = _ORIGINAL_LOAD(context, position, models)
    if state.get("fully_exact") and _looks_like_headword(state):
        sequence = _extract_headword_sequence(state, models)
        if sequence:
            _TRACKER.exact_sequence_for_active = sequence
            _STATS["observed_headwords"] += 1
    return state


def _print_stats() -> None:
    print(
        "previous-headword-sequence-summary: "
        f"calls={_STATS['calls']} calls_with_previous={_STATS['calls_with_previous']} "
        f"observed_headwords={_STATS['observed_headwords']} committed_headwords={_STATS['committed_headwords']} "
        f"sequence_states={_STATS['sequence_states']} expected_promotions={_STATS['expected_promotions']} "
        f"expected_fits={_STATS['expected_fits']} break_fits={_STATS['break_fits']} "
        f"sequence_diverged={_STATS['sequence_diverged']} states={_STATS['states']} placements={_STATS['placements']}",
        flush=True,
    )


_ORIGINAL_ORDINARY = context_anchor._ORIGINAL
_ORIGINAL_FIXED = context_anchor._fixed_baseline_exact_cover


def main() -> int:
    original_load = page_editor._load_owned_row_state
    context_anchor._ORIGINAL = _sequence_exact_cover
    context_anchor._fixed_baseline_exact_cover = _sequence_fixed_baseline_exact_cover
    page_editor._load_owned_row_state = _tracked_load
    try:
        result = downstream.main()
    finally:
        context_anchor._ORIGINAL = _ORIGINAL_ORDINARY
        context_anchor._fixed_baseline_exact_cover = _ORIGINAL_FIXED
        page_editor._load_owned_row_state = original_load
        if hasattr(priority._tls, "previous_headword_glyph_sequence"):
            del priority._tls.previous_headword_glyph_sequence
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
