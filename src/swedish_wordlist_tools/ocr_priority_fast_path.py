from __future__ import annotations

"""Result-neutral candidate ordering for the anchored exact glyph fast path.

The search space is unchanged: layout and previous typography only decide which
facit models are tried first. If a preferred class does not fit exactly, every
other model remains available as before.
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


def _is_homonym_model(model: GlyphModel) -> bool:
    return len(model.label) == 1 and model.label in "123456789"


def _model_order_key(
    model: GlyphModel,
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
) -> tuple[int, int, int, str, str]:
    """Order candidates without ever excluding one.

    Position wins at row start. Afterwards local typography continuity wins.
    On continuation rows headword-bold is deliberately last unless it was just
    proved by the previous glyph.
    """
    priority = 1
    if first_glyph:
        if row_kind == "homonym":
            if _is_homonym_model(model):
                priority = 0
            elif model.style == "headword-bold":
                priority = 2
        elif row_kind == "headword":
            priority = 0 if model.style == "headword-bold" else 1
        elif row_kind == "continuation":
            priority = 2 if model.style == "headword-bold" else 1
    elif previous_style is not None:
        if model.style == previous_style:
            priority = 0
        elif row_kind == "continuation" and model.style == "headword-bold":
            priority = 2

    return (
        priority,
        -len(model.pixels),
        -int(model.sources),
        model.label,
        model.style,
    )


def prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Anchored exact cover with layout/style-prioritized candidate order.

    This intentionally mirrors ``ocr_glyph_gap_matcher.fast_exact_cover``.
    Only candidate order differs; all exactness tests and fallback semantics are
    unchanged.
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
    failed: set[tuple[frozenset[tuple[int, int]], int | None]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, baseline)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        ordered = sorted(
            prepared,
            key=lambda row: _model_order_key(
                row[0],
                first_glyph=first_glyph,
                previous_style=previous_style,
                row_kind=row_kind,
            ),
        )

        for model, min_x, left_pixels in ordered:
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                if baseline is not None and candidate_baseline != baseline:
                    continue
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                placed = frozenset(
                    (x0 + x, candidate_baseline + y)
                    for x, y in model.pixels
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
                tail = search(
                    frozenset(remaining.difference(placed)),
                    candidate_baseline if baseline is None else baseline,
                    model.style,
                )
                if tail is not None:
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, None)
    stats["placements_tested"] += placements_tested
    if chosen is None:
        return None
    stats["successful_calls"] += 1
    selected = sorted(chosen, key=lambda match: (match.x, match.baseline, match.label, match.style))
    baseline = selected[0].baseline
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
    matches = sorted(state.get("matches") or [], key=lambda m: (m.x, m.baseline))
    if not matches:
        return
    crop_left = int(state["crop_box"][0])
    column = int(state["column"])
    first = matches[0]
    absolute_x = crop_left + int(first.x)

    if first.style == "headword-bold":
        _column_counters(context, "priority_headword_x_counts", column)[absolute_x] += 1

    if _is_homonym_model(first):
        # A homonym number is layout evidence only when the same row also has
        # headword typography after it; ordinary digits elsewhere must not teach
        # the homonym margin.
        if any(match.x > first.x and match.style == "headword-bold" for match in matches[1:]):
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
