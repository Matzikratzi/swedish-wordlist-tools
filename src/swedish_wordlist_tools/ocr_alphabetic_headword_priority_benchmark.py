from __future__ import annotations

"""Benchmark result-neutral alphabetic candidate priority for headwords.

The previous exact bold headword is used only as an ordering hint for the next
headword. While the current decoded bold prefix still equals the previous
headword prefix, candidates that reproduce the previous next letter are tried
first. Full and half word-boundary marks (``|`` and ``·``) may occur without
consuming an alphabetic character, so they do not break the prefix relation.

No candidate is removed and all exact-cover acceptance rules are unchanged.
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


def _letters(label: str) -> str:
    return "".join(ch for ch in str(label).casefold() if ch.isalpha())


def _alphabet_rows(
    rows,
    *,
    prefix: str,
    previous: str | None,
    active: bool,
):
    """Stable two-tier ordering: expected continuation/breaks, then original."""
    if not active or not previous or not previous.startswith(prefix) or len(prefix) >= len(previous):
        yield from rows
        return

    expected = previous[len(prefix)]
    promoted = 0
    buffered = []
    for row in rows:
        model = row[0]
        chars = _letters(model.label)
        if model.label in _BREAKS or (chars and chars[0] == expected):
            promoted += 1
            yield row
        else:
            buffered.append(row)
    _STATS["priority_states"] += 1
    _STATS["promoted_candidates"] += promoted
    yield from buffered


def _alpha_exact_cover(
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
    previous = getattr(priority._tls, "alphabet_previous", None)
    if row_kind not in {"headword", "homonym"}:
        previous = None
    if previous:
        _STATS["calls_with_previous"] += 1

    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
        alphabet_prefix: str,
        alphabet_active: bool,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, baseline, leading_homonym_seen)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        base_rows = cached._iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        )
        rows = _alphabet_rows(
            base_rows,
            prefix=alphabet_prefix,
            previous=previous,
            active=alphabet_active,
        )

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
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                placed = frozenset((x0 + x, candidate_baseline + y) for x, y in model.pixels)
                if not placed.issubset(remaining):
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
                    next_prefix = alphabet_prefix
                    next_active = alphabet_active
                else:
                    next_baseline = candidate_baseline if baseline is None else baseline
                    saw_homonym = leading_homonym_seen
                    typography = priority._typographic_style(model.style)
                    if alphabet_active and (typography == "bold" or model.label in _BREAKS):
                        next_prefix = alphabet_prefix + _letters(model.label)
                        next_active = True
                    else:
                        next_prefix = alphabet_prefix
                        next_active = False

                tail = search(
                    frozenset(remaining.difference(placed)),
                    next_baseline,
                    priority._typographic_style(model.style),
                    saw_homonym,
                    next_prefix,
                    next_active,
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, None, False, "", bool(previous))
    _STATS["calls"] += 1
    _STATS["placements"] += placements_tested
    _STATS["states"] += states
    if chosen is None:
        return None

    selected = sorted(chosen, key=lambda match: (match.x, match.baseline, match.label, str(match.style)))
    if row_kind == "homonym" and selected and priority._is_homonym_match(selected[0]):
        normal = next((m for m in selected[1:] if not priority._is_homonym_match(m)), None)
        baseline = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline = selected[0].baseline
    return baseline, selected, placements_tested


def _alpha_fixed_baseline_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    fixed_baseline: int,
    *,
    max_states: int = 20000,
):
    if not ink:
        return None

    page_candidates = cached._bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    previous = getattr(priority._tls, "alphabet_previous", None)
    if row_kind not in {"headword", "homonym"}:
        previous = None
    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], bool]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        previous_style: str | None,
        leading_homonym_seen: bool,
        alphabet_prefix: str,
        alphabet_active: bool,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, leading_homonym_seen)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        base_rows = cached._iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=True,
        )
        rows = _alphabet_rows(base_rows, prefix=alphabet_prefix, previous=previous, active=alphabet_active)

        for model, min_x, left_pixels in rows:
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                is_leading_homonym = (
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
                )
                if not is_leading_homonym and candidate_baseline != fixed_baseline:
                    continue
                if candidate_baseline < -model.min_y or candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                placed = frozenset((x0 + x, candidate_baseline + y) for x, y in model.pixels)
                if not placed.issubset(remaining):
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
                typography = priority._typographic_style(model.style)
                if is_leading_homonym:
                    next_prefix = alphabet_prefix
                    next_active = alphabet_active
                elif alphabet_active and (typography == "bold" or model.label in _BREAKS):
                    next_prefix = alphabet_prefix + _letters(model.label)
                    next_active = True
                else:
                    next_prefix = alphabet_prefix
                    next_active = False
                tail = search(
                    frozenset(remaining.difference(placed)),
                    typography,
                    leading_homonym_seen or is_leading_homonym,
                    next_prefix,
                    next_active,
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, False, "", bool(previous))
    if chosen is None:
        return None
    selected = sorted(chosen, key=lambda match: (match.x, match.baseline, match.label, str(match.style)))
    return fixed_baseline, selected, placements_tested, states


@dataclass
class _Tracker:
    previous: str | None = None
    active_key: tuple[int, int, int] | None = None
    previous_for_active: str | None = None
    exact_headword_for_active: str | None = None


_TRACKER = _Tracker()
_ORIGINAL_LOAD = page_editor._load_owned_row_state


def _extract_headword(state: dict) -> str | None:
    matches = list(state.get("matches") or state.get("selected") or [])
    matches.sort(key=lambda m: (int(getattr(m, "x", 0)), int(getattr(m, "baseline", 0))))
    letters = []
    started = False
    for match in matches:
        if priority._is_homonym_match(match) and not started:
            continue
        label = str(getattr(match, "label", ""))
        typography = priority._typographic_style(getattr(match, "style", ""))
        if typography == "bold" or (started and label in _BREAKS):
            started = True
            letters.append(_letters(label))
            continue
        if started:
            break
    word = "".join(letters)
    return word or None


def _tracked_load(context: dict, position: tuple[int, int], models):
    page = int(context.get("page_number", -1))
    key = (page, int(position[0]), int(position[1]))
    if key != _TRACKER.active_key:
        if _TRACKER.exact_headword_for_active:
            _TRACKER.previous = _TRACKER.exact_headword_for_active
            _STATS["committed_headwords"] += 1
        _TRACKER.active_key = key
        _TRACKER.previous_for_active = _TRACKER.previous
        _TRACKER.exact_headword_for_active = None

    priority._tls.alphabet_previous = _TRACKER.previous_for_active
    state = _ORIGINAL_LOAD(context, position, models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    if state.get("fully_exact") and row_kind in {"headword", "homonym"}:
        word = _extract_headword(state)
        if word:
            _TRACKER.exact_headword_for_active = word
            _STATS["observed_headwords"] += 1
    return state


def _print_stats() -> None:
    print(
        "alphabet-priority-summary: "
        f"calls={_STATS['calls']} calls_with_previous={_STATS['calls_with_previous']} "
        f"priority_states={_STATS['priority_states']} promoted_candidates={_STATS['promoted_candidates']} "
        f"observed_headwords={_STATS['observed_headwords']} committed_headwords={_STATS['committed_headwords']} "
        f"states={_STATS['states']} placements={_STATS['placements']}",
        flush=True,
    )


def main() -> int:
    original_context_ordinary = context_anchor._ORIGINAL
    original_context_fixed = context_anchor._fixed_baseline_exact_cover
    original_load = page_editor._load_owned_row_state
    context_anchor._ORIGINAL = _alpha_exact_cover
    context_anchor._fixed_baseline_exact_cover = _alpha_fixed_baseline_exact_cover
    page_editor._load_owned_row_state = _tracked_load
    try:
        result = downstream.main()
    finally:
        context_anchor._ORIGINAL = original_context_ordinary
        context_anchor._fixed_baseline_exact_cover = original_context_fixed
        page_editor._load_owned_row_state = original_load
        if hasattr(priority._tls, "alphabet_previous"):
            del priority._tls.alphabet_previous
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
