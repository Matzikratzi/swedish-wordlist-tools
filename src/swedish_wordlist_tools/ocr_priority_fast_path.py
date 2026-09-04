from __future__ import annotations

"""Result-neutral candidate ordering for the anchored exact glyph fast path.

The search space is unchanged: layout and previous typography only decide which
facit raster classes are tried first. Models with identical raster geometry keep
the old canonical order so metadata/label choice cannot change merely because a
layout hint was added.
"""

from collections import Counter
from threading import local
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, Match

_tls = local()


def reset_priority_stats() -> None:
    _tls.stats = {
        "calls": 0,
        "successful_calls": 0,
        "placements_tested": 0,
        "headword_hints": 0,
        "homonym_hints": 0,
        "continuation_hints": 0,
        "unknown_hints": 0,
    }


def priority_stats() -> dict[str, int]:
    stats = getattr(_tls, "stats", None)
    if stats is None:
        reset_priority_stats()
        stats = _tls.stats
    return dict(stats)


def set_row_priority_hint(kind: str | None) -> None:
    kind = str(kind or "unknown")
    if kind not in {"headword", "homonym", "continuation", "unknown"}:
        kind = "unknown"
    _tls.row_kind = kind


def _stats() -> dict[str, int]:
    stats = getattr(_tls, "stats", None)
    if stats is None:
        reset_priority_stats()
        stats = _tls.stats
    return stats


def _typographic_style(style) -> str:
    """Return roman/italic/bold without changing the semantic facit role."""
    typography = getattr(style, "typographic_style", None)
    if typography in {"roman", "italic", "bold"}:
        return str(typography)
    raw = str(style)
    if raw in {"roman", "italic", "bold"}:
        return raw
    if raw == "headword-bold":
        return "bold"
    if raw in {"inflection-italic", "context-italic"}:
        return "italic"
    if raw in {"pos-roman", "definition-roman", "inflection-label-roman"}:
        return "roman"
    return "unknown"


def _is_headword_model(model: GlyphModel) -> bool:
    return str(model.style) == "headword-bold" or _typographic_style(model.style) == "bold"


def _is_headword_match(match) -> bool:
    style = getattr(match, "style", None)
    return str(style) == "headword-bold" or _typographic_style(style) == "bold"


def _is_homonym_model(model: GlyphModel) -> bool:
    return len(model.label) == 1 and model.label in "123456789"


def _is_homonym_match(match) -> bool:
    label = str(getattr(match, "label", ""))
    return len(label) == 1 and label in "123456789"


def _canonical_model_key(model: GlyphModel) -> tuple[int, int, str, str]:
    """The pre-priority fast path's deterministic model ordering."""
    return (-len(model.pixels), -int(model.sources), model.label, str(model.style))


def _raster_key(model: GlyphModel) -> tuple[tuple[int, int], ...]:
    """Normalized exact raster identity, independent of label/role metadata."""
    return tuple(sorted((int(x), int(y)) for x, y in model.pixels))


def _priority_class(
    model: GlyphModel,
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
    leading_homonym_seen: bool,
    baseline_established: bool,
) -> int:
    priority = 1
    typography = _typographic_style(model.style)
    if first_glyph:
        if row_kind == "homonym":
            if _is_homonym_model(model):
                priority = 0
            elif _is_headword_model(model):
                priority = 2
        elif row_kind == "headword":
            priority = 0 if _is_headword_model(model) else 1
        elif row_kind == "continuation":
            priority = 2 if _is_headword_model(model) else 1
    elif row_kind == "homonym" and leading_homonym_seen and not baseline_established:
        priority = 0 if _is_headword_model(model) else 1
    elif previous_style is not None:
        if typography == previous_style:
            priority = 0
        elif row_kind == "continuation" and _is_headword_model(model):
            priority = 2
    return priority


def _ordered_prepared(
    prepared: list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]],
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
    leading_homonym_seen: bool,
    baseline_established: bool,
) -> list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]]:
    """Prioritize raster classes, never metadata variants of one raster.

    The old fast path sorts models by pixel count, source count, label and role.
    If two facit models have identical normalized pixels they yield the exact
    same placement. Reordering those models can therefore alter recognized
    metadata while leaving pixel coverage unchanged. Keep their old order and
    use the best layout priority of the whole raster class only to position that
    class relative to other geometries.
    """
    groups: dict[tuple[tuple[int, int], ...], list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]]] = {}
    for row in prepared:
        groups.setdefault(_raster_key(row[0]), []).append(row)

    ordered_groups = []
    for raster, rows in groups.items():
        canonical_rows = sorted(rows, key=lambda row: _canonical_model_key(row[0]))
        class_priority = min(
            _priority_class(
                row[0],
                first_glyph=first_glyph,
                previous_style=previous_style,
                row_kind=row_kind,
                leading_homonym_seen=leading_homonym_seen,
                baseline_established=baseline_established,
            )
            for row in rows
        )
        representative = canonical_rows[0][0]
        ordered_groups.append((class_priority, _canonical_model_key(representative), raster, canonical_rows))

    ordered_groups.sort(key=lambda item: (item[0], item[1], item[2]))
    return [row for _priority, _canonical, _raster, rows in ordered_groups for row in rows]


def prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Anchored exact cover with layout/style-prioritized raster ordering.

    On a row classified as a homonym row, an exact leading homonym digit keeps
    its own facit-derived placement baseline. It does not establish the shared
    text baseline; the following non-homonym glyph does. No fixed vertical
    offset is assumed: exact facit geometry decides every placement.
    """
    if not ink:
        return None

    model_rows = [model for model in models if model.pixels]
    prepared: list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]] = []
    for model in model_rows:
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple(sorted((x, y) for x, y in model.pixels if x == min_x))
        prepared.append((model, min_x, left_pixels))

    row_kind = str(getattr(_tls, "row_kind", "unknown"))
    stats = _stats()
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
        ordered = _ordered_prepared(
            prepared,
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
                is_leading_homonym = first_glyph and row_kind == "homonym" and _is_homonym_model(model)
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
                else:
                    next_baseline = candidate_baseline if baseline is None else baseline
                    saw_homonym = leading_homonym_seen
                tail = search(
                    frozenset(remaining.difference(placed)),
                    next_baseline,
                    _typographic_style(model.style),
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
    selected = sorted(chosen, key=lambda match: (match.x, match.baseline, match.label, str(match.style)))

    if row_kind == "homonym" and selected and _is_homonym_match(selected[0]):
        normal = next((m for m in selected[1:] if not _is_homonym_match(m)), None)
        baseline = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline = selected[0].baseline

    stats["successful_calls"] += 1
    return baseline, selected, placements_tested


def _column_counters(context: dict, key: str, column: int) -> Counter[int]:
    store = context.setdefault(key, {})
    counter = store.get(column)
    if counter is None:
        counter = Counter()
        store[column] = counter
    return counter


def observe_row_layout(context: dict, state: dict) -> None:
    """Learn stable absolute x positions from already exact facit evidence."""
    raw_matches = state.get("matches") or []
    matches = [m for m in raw_matches if hasattr(m, "x") and hasattr(m, "baseline")]
    matches.sort(key=lambda m: (int(m.x), int(m.baseline)))
    if not matches:
        return
    crop_box = state.get("crop_box")
    if not crop_box:
        return
    crop_left = int(crop_box[0])
    column = int(state.get("column", 0))
    first = matches[0]
    absolute_x = crop_left + int(first.x)

    if _is_headword_match(first):
        _column_counters(context, "priority_headword_x_counts", column)[absolute_x] += 1

    if _is_homonym_match(first):
        if any(int(match.x) > int(first.x) and _is_headword_match(match) for match in matches[1:]):
            _column_counters(context, "priority_homonym_x_counts", column)[absolute_x] += 1


def _most_common_x(context: dict, key: str, column: int) -> int | None:
    counter = (context.get(key) or {}).get(column)
    if not counter:
        return None
    return int(counter.most_common(1)[0][0])


def classify_row_start(context: dict, position: tuple[int, int]) -> str:
    """Classify current physical row start using page ownership and learned x."""
    column, row_index = map(int, position)
    columns = context.get("row_map", {}).get("columns") or []
    if not 0 <= column < len(columns):
        return "unknown"
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        return "unknown"

    owners = context.get("pixel_owners")
    if owners is None:
        return "unknown"
    row = rows[row_index]
    left = max(0, int((context.get("column_content_lefts") or {}).get(column) or columns[column].get("crop_left", columns[column].get("left", 0))))
    right = min(owners.width, int(columns[column].get("crop_right", columns[column].get("right", owners.width))))
    top = max(0, int(row.get("page_top", 0)))
    bottom = min(owners.height, int(row.get("page_bottom", owners.height)))
    code = owners.row_code(row_index)

    start_x = None
    for x in range(left, right):
        if any(owners.data[y * owners.width + x] == code for y in range(top, bottom)):
            start_x = x
            break
    if start_x is None:
        return "unknown"

    homonym_x = _most_common_x(context, "priority_homonym_x_counts", column)
    if homonym_x is not None and start_x == homonym_x:
        return "homonym"
    headword_x = _most_common_x(context, "priority_headword_x_counts", column)
    if headword_x is not None:
        return "headword" if start_x == headword_x else "continuation"
    return "unknown"
