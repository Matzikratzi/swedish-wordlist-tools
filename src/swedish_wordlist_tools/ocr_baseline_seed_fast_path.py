from __future__ import annotations

"""Conservative baseline-seeded exact-cover fast path.

Headword rows normally start with a bold glyph at a stable x position.  Before
running the full exact-cover search, probe only exact bold placements at the
leftmost ink anchor.  If all exact bold placements imply one baseline, try the
full search with that baseline fixed.  Homonym rows first peel an exact leading
homonym digit and then probe the following bold headword glyph.

The seed is only an optimization.  If the seeded search fails, the ordinary
page-cached exact-cover search is run unchanged, so the accepted result set is
identical to the old implementation.
"""

from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_page_cached_fast_path import (
    _PageCandidates,
    _bound_page_candidates,
    _iter_candidates,
    page_cached_prioritized_fast_exact_cover as _ordinary_exact_cover,
)


def _anchor_x_y(ink: frozenset[tuple[int, int]]) -> tuple[int, int]:
    x = min(px for px, _py in ink)
    y = min(py for px, py in ink if px == x)
    return x, y


def _exact_anchor_placements(
    ink: frozenset[tuple[int, int]],
    *,
    width: int,
    height: int,
    prepared,
    expected_label: str | None = None,
) -> list[tuple[GlyphModel, int, frozenset[tuple[int, int]]]]:
    """Return exact model placements whose left edge owns the ink anchor."""
    if not ink:
        return []
    anchor_x, anchor_y = _anchor_x_y(ink)
    out: list[tuple[GlyphModel, int, frozenset[tuple[int, int]]]] = []
    for model, min_x, left_pixels in prepared:
        if expected_label is not None and str(model.label) != expected_label:
            continue
        x0 = anchor_x - min_x
        if x0 < 0 or x0 + model.width > width:
            continue
        for _mx, my in left_pixels:
            baseline = anchor_y - my
            if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                continue
            placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
            if placed.issubset(ink):
                out.append((model, baseline, placed))
    return out


def _expected_initial() -> str | None:
    value = getattr(priority._tls, "expected_headword_initial", None)
    if value is None:
        return None
    value = str(value)
    return value if len(value) == 1 else None


def set_expected_headword_initial(value: str | None) -> None:
    """Optional hook for a JSONL-derived known headword first letter."""
    if value is None:
        priority._tls.expected_headword_initial = None
        return
    value = str(value)
    priority._tls.expected_headword_initial = value if len(value) == 1 else None


def _headword_seed_baseline(
    target: frozenset[tuple[int, int]],
    *,
    width: int,
    height: int,
    candidates: _PageCandidates,
    row_kind: str,
) -> int | None:
    """Return one uniquely proven normal-text baseline, otherwise None."""
    expected = _expected_initial()
    baselines: set[int] = set()

    if row_kind == "headword":
        placements = _exact_anchor_placements(
            target,
            width=width,
            height=height,
            prepared=candidates.bold,
            expected_label=expected,
        )
        baselines.update(baseline for _model, baseline, _placed in placements)
        return next(iter(baselines)) if len(baselines) == 1 else None

    if row_kind != "homonym":
        return None

    homonym_placements = _exact_anchor_placements(
        target,
        width=width,
        height=height,
        prepared=candidates.homonym,
    )
    for _digit, _digit_baseline, digit_pixels in homonym_placements:
        remaining = frozenset(target.difference(digit_pixels))
        if not remaining:
            continue
        bold_placements = _exact_anchor_placements(
            remaining,
            width=width,
            height=height,
            prepared=candidates.bold,
            expected_label=expected,
        )
        baselines.update(baseline for _model, baseline, _placed in bold_placements)
    return next(iter(baselines)) if len(baselines) == 1 else None


def _seeded_search(
    target: frozenset[tuple[int, int]],
    *,
    width: int,
    height: int,
    candidates: _PageCandidates,
    row_kind: str,
    seed_baseline: int,
    max_states: int,
) -> tuple[tuple[Match, ...] | None, int, int]:
    """Run the ordinary search logic while fixing only the normal text baseline."""
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
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

        anchor_x, anchor_y = _anchor_x_y(remaining)
        first_glyph = len(remaining) == len(target)
        for model, min_x, left_pixels in _iter_candidates(
            candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                is_leading_homonym = (
                    first_glyph
                    and row_kind == "homonym"
                    and priority._is_homonym_model(model)
                )
                if baseline is not None and candidate_baseline != baseline:
                    continue
                # A homonym digit keeps its own placement.  The first normal
                # headword glyph must land on the seed baseline.
                if baseline is None and not is_leading_homonym and candidate_baseline != seed_baseline:
                    continue
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
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
                else:
                    next_baseline = candidate_baseline if baseline is None else baseline
                    saw_homonym = leading_homonym_seen
                tail = search(
                    frozenset(remaining.difference(placed)),
                    next_baseline,
                    priority._typographic_style(model.style),
                    saw_homonym,
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail
        failed.add(state)
        return None

    return search(target, None, None, False), placements_tested, states


def baseline_seeded_page_cached_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Try a uniquely proven headword baseline, then fall back unchanged."""
    if not ink:
        return None

    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    if row_kind not in {"headword", "homonym"}:
        return _ordinary_exact_cover(ink, width, height, models, max_states=max_states)

    candidates = _bound_page_candidates(models)
    target = frozenset(ink)
    stats = priority._stats()
    stats["baseline_seed_probes"] = stats.get("baseline_seed_probes", 0) + 1
    seed = _headword_seed_baseline(
        target,
        width=width,
        height=height,
        candidates=candidates,
        row_kind=row_kind,
    )
    if seed is None:
        return _ordinary_exact_cover(ink, width, height, models, max_states=max_states)

    stats["baseline_seed_unique"] = stats.get("baseline_seed_unique", 0) + 1
    # Keep a failed seed cheap.  A correct baseline usually succeeds with a
    # tiny search tree; a contaminated/misclassified row should fall back long
    # before consuming the ordinary 20k-state budget.
    seed_budget = min(int(max_states), 2000)
    chosen, placements, states = _seeded_search(
        target,
        width=width,
        height=height,
        candidates=candidates,
        row_kind=row_kind,
        seed_baseline=seed,
        max_states=seed_budget,
    )
    stats["baseline_seed_states"] = stats.get("baseline_seed_states", 0) + states
    stats["baseline_seed_placements"] = stats.get("baseline_seed_placements", 0) + placements

    if chosen is None:
        stats["baseline_seed_fallbacks"] = stats.get("baseline_seed_fallbacks", 0) + 1
        return _ordinary_exact_cover(ink, width, height, models, max_states=max_states)

    selected = sorted(
        chosen,
        key=lambda match: (match.x, match.baseline, match.label, str(match.style)),
    )
    if row_kind == "homonym" and selected and priority._is_homonym_match(selected[0]):
        normal = next(
            (match for match in selected[1:] if not priority._is_homonym_match(match)),
            None,
        )
        baseline = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline = selected[0].baseline

    # Mirror the public counters of one successful ordinary fast-path call.
    stats["calls"] += 1
    stats[f"{row_kind}_hints"] += 1
    stats["successful_calls"] += 1
    stats["placements_tested"] += placements
    stats["baseline_seed_success"] = stats.get("baseline_seed_success", 0) + 1
    return baseline, selected, placements
