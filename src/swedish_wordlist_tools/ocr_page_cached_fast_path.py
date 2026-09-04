from __future__ import annotations

"""Page-scoped preparation for the prioritized exact glyph fast path.

The facit models do not change while one page is being analysed.  Preparing
model geometry, typography buckets and raster groups once per physical page
therefore avoids repeating the same work for every row while preserving the
existing result-neutral candidate ordering.
"""

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, Match
from . import ocr_priority_fast_path as priority


_CONTEXT_KEY = "_priority_page_candidates"


@dataclass(frozen=True)
class _PageCandidates:
    models_id: int
    model_count: int
    first_model_id: int | None
    last_model_id: int | None
    homonym: tuple[tuple[GlyphModel, int, tuple[tuple[int, int], ...]], ...]
    bold: tuple[tuple[GlyphModel, int, tuple[tuple[int, int], ...]], ...]
    roman: tuple[tuple[GlyphModel, int, tuple[tuple[int, int], ...]], ...]
    italic: tuple[tuple[GlyphModel, int, tuple[tuple[int, int], ...]], ...]
    other: tuple[tuple[GlyphModel, int, tuple[tuple[int, int], ...]], ...]
    orders: object


def _model_signature(models) -> tuple[int, int, int | None, int | None]:
    try:
        count = len(models)
    except TypeError:
        return id(models), -1, None, None
    if count == 0:
        return id(models), 0, None, None
    try:
        return id(models), count, id(models[0]), id(models[-1])
    except (TypeError, KeyError):
        return id(models), count, None, None


def _build_page_candidates(models: Iterable[GlyphModel]) -> _PageCandidates:
    if not hasattr(models, "__len__") or not hasattr(models, "__getitem__"):
        models = tuple(models)

    buckets: dict[str, list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]]] = {
        "homonym": [],
        "bold": [],
        "roman": [],
        "italic": [],
        "other": [],
    }
    prepared: list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]] = []
    for model in models:
        if not model.pixels:
            continue
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple(sorted((x, y) for x, y in model.pixels if x == min_x))
        row = (model, min_x, left_pixels)
        prepared.append(row)
        if priority._is_homonym_model(model):
            bucket = "homonym"
        else:
            typography = priority._typographic_style(model.style)
            bucket = typography if typography in {"bold", "roman", "italic"} else "other"
        buckets[bucket].append(row)

    models_id, model_count, first_model_id, last_model_id = _model_signature(models)
    return _PageCandidates(
        models_id=models_id,
        model_count=model_count,
        first_model_id=first_model_id,
        last_model_id=last_model_id,
        homonym=tuple(buckets["homonym"]),
        bold=tuple(buckets["bold"]),
        roman=tuple(buckets["roman"]),
        italic=tuple(buckets["italic"]),
        other=tuple(buckets["other"]),
        orders=priority._PreparedCandidateOrders(prepared),
    )


def bind_page_candidates(context: dict, models: Iterable[GlyphModel]) -> _PageCandidates:
    """Bind one immutable candidate preparation to the current page context."""
    signature = _model_signature(models)
    cached = context.get(_CONTEXT_KEY)
    if cached is None or (
        cached.models_id,
        cached.model_count,
        cached.first_model_id,
        cached.last_model_id,
    ) != signature:
        cached = _build_page_candidates(models)
        context[_CONTEXT_KEY] = cached
        stats = priority._stats()
        stats["page_prepares"] = stats.get("page_prepares", 0) + 1
        context["priority_page_bucket_counts"] = {
            "homonym": len(cached.homonym),
            "bold": len(cached.bold),
            "roman": len(cached.roman),
            "italic": len(cached.italic),
            "other": len(cached.other),
        }
    priority._tls.page_candidates = cached
    return cached


def _bound_page_candidates(models: Iterable[GlyphModel]) -> _PageCandidates:
    signature = _model_signature(models)
    cached = getattr(priority._tls, "page_candidates", None)
    if cached is not None and (
        cached.models_id,
        cached.model_count,
        cached.first_model_id,
        cached.last_model_id,
    ) == signature:
        return cached
    # Direct callers outside the shared page loader retain the old behaviour:
    # they get a private preparation rather than accidentally reusing stale page
    # state from some previous call.
    return _build_page_candidates(models)


def page_cached_prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """The existing prioritized exact cover using page-prepared candidates."""
    if not ink:
        return None

    page_candidates = _bound_page_candidates(models)
    candidate_orders = page_candidates.orders

    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    stats = priority._stats()
    stats["calls"] += 1
    stats[f"{row_kind}_hints"] += 1

    target = frozenset(ink)
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

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        ordered = candidate_orders.ordered(
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        )

        for model, min_x, left_pixels in ordered:
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
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, None, False)
    stats["placements_tested"] += placements_tested
    if chosen is None:
        return None
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

    stats["successful_calls"] += 1
    return baseline, selected, placements_tested
