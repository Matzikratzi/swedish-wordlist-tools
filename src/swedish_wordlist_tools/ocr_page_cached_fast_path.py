from __future__ import annotations

"""Page-scoped preparation for the prioritized exact glyph fast path.

The facit does not change while one page is analysed. Prepare model geometry,
typography buckets and raster grouping once per page, then let the recursive
search iterate those immutable buckets directly. No candidate order is built
inside ordinary row analysis.
"""

from dataclasses import dataclass
from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit, register_bucket


_CONTEXT_KEY = "_priority_page_candidates"
_Prepared = tuple[GlyphModel, int, tuple[tuple[int, int], ...]]


@dataclass(frozen=True)
class _PageCandidates:
    models_id: int
    model_count: int
    first_model_id: int | None
    last_model_id: int | None
    homonym: tuple[_Prepared, ...]
    bold: tuple[_Prepared, ...]
    roman: tuple[_Prepared, ...]
    italic: tuple[_Prepared, ...]
    other: tuple[_Prepared, ...]
    cross_bucket_raster: bool
    fallback_orders: object


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


def _bucket_name(model: GlyphModel) -> str:
    if priority._is_homonym_model(model):
        return "homonym"
    typography = priority._typographic_style(model.style)
    return typography if typography in {"bold", "roman", "italic"} else "other"


def _canonicalize_bucket(rows: list[_Prepared]) -> tuple[_Prepared, ...]:
    """Keep exact-raster models contiguous in the old canonical order."""
    groups: dict[tuple[tuple[int, int], ...], list[_Prepared]] = {}
    for row in rows:
        groups.setdefault(priority._raster_key(row[0]), []).append(row)

    compiled = []
    for raster, group_rows in groups.items():
        canonical_rows = tuple(
            sorted(group_rows, key=lambda row: priority._canonical_model_key(row[0]))
        )
        compiled.append(
            (
                priority._canonical_model_key(canonical_rows[0][0]),
                raster,
                canonical_rows,
            )
        )
    compiled.sort(key=lambda item: (item[0], item[1]))
    return tuple(row for _canonical, _raster, group_rows in compiled for row in group_rows)


def _build_page_candidates(models: Iterable[GlyphModel]) -> _PageCandidates:
    if not hasattr(models, "__len__") or not hasattr(models, "__getitem__"):
        models = tuple(models)

    raw_buckets: dict[str, list[_Prepared]] = {
        "homonym": [],
        "bold": [],
        "roman": [],
        "italic": [],
        "other": [],
    }
    prepared: list[_Prepared] = []
    raster_buckets: dict[tuple[tuple[int, int], ...], set[str]] = {}

    for model in models:
        if not model.pixels:
            continue
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple(sorted((x, y) for x, y in model.pixels if x == min_x))
        row = (model, min_x, left_pixels)
        prepared.append(row)
        bucket = _bucket_name(model)
        raw_buckets[bucket].append(row)
        raster_buckets.setdefault(priority._raster_key(model), set()).add(bucket)

    buckets = {name: _canonicalize_bucket(rows) for name, rows in raw_buckets.items()}
    cross_bucket_raster = any(len(names) > 1 for names in raster_buckets.values())
    models_id, model_count, first_model_id, last_model_id = _model_signature(models)
    return _PageCandidates(
        models_id=models_id,
        model_count=model_count,
        first_model_id=first_model_id,
        last_model_id=last_model_id,
        homonym=buckets["homonym"],
        bold=buckets["bold"],
        roman=buckets["roman"],
        italic=buckets["italic"],
        other=buckets["other"],
        cross_bucket_raster=cross_bucket_raster,
        fallback_orders=priority._PreparedCandidateOrders(prepared),
    )


def _register_popularity_candidates(cached: _PageCandidates) -> None:
    register_bucket("homonym", cached.homonym, typography_of=priority._typographic_style)
    register_bucket("bold", cached.bold, typography_of=priority._typographic_style)
    register_bucket("roman", cached.roman, typography_of=priority._typographic_style)
    register_bucket("italic", cached.italic, typography_of=priority._typographic_style)
    register_bucket("other", cached.other, typography_of=priority._typographic_style)


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
        context["priority_cross_bucket_raster"] = cached.cross_bucket_raster
        _register_popularity_candidates(cached)
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
    cached = _build_page_candidates(models)
    _register_popularity_candidates(cached)
    return cached


def _bucket_sequence(
    candidates: _PageCandidates,
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
    leading_homonym_seen: bool,
    baseline_established: bool,
) -> tuple[tuple[_Prepared, ...], ...]:
    """Return references to page buckets only; never concatenate or sort them."""
    h = candidates.homonym
    b = candidates.bold
    r = candidates.roman
    i = candidates.italic
    o = candidates.other

    if first_glyph:
        if row_kind == "homonym":
            return (h, b, r, i, o)
        if row_kind == "headword":
            return (b, r, i, o, h)
        if row_kind == "continuation":
            return (r, i, o, h, b)
        return (r, i, o, b, h)

    if row_kind == "homonym" and leading_homonym_seen and not baseline_established:
        return (b, r, i, o, h)

    if previous_style == "bold":
        return (b, r, i, o, h)
    if previous_style == "italic":
        if row_kind == "continuation":
            return (i, r, o, h, b)
        return (i, r, o, b, h)
    if previous_style == "roman":
        if row_kind == "continuation":
            return (r, i, o, h, b)
        return (r, i, o, b, h)

    if row_kind == "continuation":
        return (r, i, o, h, b)
    return (r, i, o, b, h)


def _iter_candidates(
    candidates: _PageCandidates,
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
    leading_homonym_seen: bool,
    baseline_established: bool,
):
    if candidates.cross_bucket_raster:
        # A raster represented in more than one bucket can make bucket order
        # choose different metadata for the same pixels. Preserve the old
        # canonical ordering for that unusual/ambiguous facit state.
        yield from candidates.fallback_orders.ordered(
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline_established,
        )
        return

    for bucket in _bucket_sequence(
        candidates,
        first_glyph=first_glyph,
        previous_style=previous_style,
        row_kind=row_kind,
        leading_homonym_seen=leading_homonym_seen,
        baseline_established=baseline_established,
    ):
        yield from bucket


def page_cached_prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Anchored exact cover iterating immutable page buckets directly."""
    if not ink:
        return None

    page_candidates = _bound_page_candidates(models)
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

        for model, min_x, left_pixels in _iter_candidates(
            page_candidates,
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
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
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
                    record_model_hit(model)
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
