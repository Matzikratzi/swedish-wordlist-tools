from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _components(points: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
    out: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            x, y = stack.pop()
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p in remaining:
                    remaining.remove(p)
                    comp.add(p)
                    stack.append(p)
        out.append(comp)
    return out


def _xspan(points: set[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in points]
    return min(xs), max(xs)


def _merge_overlapping_x(components: list[set[tuple[int, int]]]) -> list[set[tuple[int, int]]]:
    """Merge detached marks with bodies, and preserve touching glyph clusters."""
    groups = [set(c) for c in components]
    changed = True
    while changed:
        changed = False
        out: list[set[tuple[int, int]]] = []
        while groups:
            current = groups.pop()
            a0, a1 = _xspan(current)
            rest: list[set[tuple[int, int]]] = []
            for other in groups:
                b0, b1 = _xspan(other)
                if max(a0, b0) <= min(a1, b1):
                    current.update(other)
                    a0, a1 = _xspan(current)
                    changed = True
                else:
                    rest.append(other)
            groups = rest
            out.append(current)
        groups = out
    return sorted(groups, key=lambda c: (_xspan(c)[0], min(y for _, y in c)))


def unknown_groups(row: dict[str, Any]) -> list[set[tuple[int, int]]]:
    points = {tuple(map(int, p)) for p in row.get("unexplained") or []}
    if not points:
        return []
    return _merge_overlapping_x(_components(points))


def _shape(points: set[tuple[int, int]], baseline: int) -> tuple[tuple[int, int], ...]:
    minx = min(x for x, _ in points)
    return tuple(sorted((x - minx, y - baseline) for x, y in points))


def _nearest_style(row: dict[str, Any], group: set[tuple[int, int]]) -> str:
    gx0, gx1 = _xspan(group)
    gc = (gx0 + gx1) / 2
    best: tuple[float, str] | None = None
    for match in row.get("exact") or []:
        pixels = {tuple(p) for p in match.get("pixels") or []}
        if not pixels:
            continue
        x0, x1 = _xspan(pixels)
        dist = abs(((x0 + x1) / 2) - gc)
        style = str(match.get("style") or "")
        if style and (best is None or dist < best[0]):
            best = (dist, style)
    return best[1] if best else "bold"


def _suffix(style: str) -> str:
    return {"bold": "b", "roman": "r", "italic": "i"}.get(style, "b")


def _split_chunk(chunk: str, count: int) -> list[str]:
    if count <= 0:
        return []
    if count == 1:
        return [chunk]
    if len(chunk) == count:
        return list(chunk)
    return [chunk] + [""] * (count - 1)


def _jsonl_group_suggestions(row: dict[str, Any], groups: list[set[tuple[int, int]]]) -> list[str]:
    hint = row.get("jsonl_hint") or {}
    reference = str(hint.get("text") or "")
    if not reference or not groups:
        return [""] * len(groups)

    group_index = {id(g): i for i, g in enumerate(groups)}
    elements: list[tuple[int, str, Any]] = []
    for g in groups:
        elements.append((_xspan(g)[0], "unknown", g))
    for m in row.get("exact") or []:
        pixels = {tuple(p) for p in m.get("pixels") or []}
        if pixels and m.get("label"):
            elements.append((_xspan(pixels)[0], "known", m))
    elements.sort(key=lambda item: item[0])

    result = [""] * len(groups)
    cursor = 0
    pending: list[set[tuple[int, int]]] = []
    folded = reference.casefold()

    def assign(chunk: str) -> None:
        nonlocal pending
        pieces = _split_chunk(chunk, len(pending))
        for g, text in zip(pending, pieces):
            if text:
                result[group_index[id(g)]] = text
        pending = []

    for _, kind, obj in elements:
        if kind == "unknown":
            pending.append(obj)
            continue
        label = str(obj.get("label") or "")
        if not label:
            continue
        pos = folded.find(label.casefold(), cursor)
        if pos < 0:
            continue
        assign(reference[cursor:pos])
        cursor = pos + len(label)
    assign(reference[cursor:])

    for i, text in enumerate(result):
        if text:
            result[i] = f"{text}{{{_suffix(_nearest_style(row, groups[i]))}}}"
    return result


def _touches_horizontal_edge(group: set[tuple[int, int]], width: int) -> bool:
    """A review glyph touching either crop edge may be clipped and is unsafe."""
    if width <= 0 or not group:
        return True
    x0, x1 = _xspan(group)
    return x0 <= 0 or x1 >= width - 1


def _shift_pixels(pixels: list[list[int]] | list[tuple[int, int]], y0: int) -> list[list[int]]:
    return [[int(x), int(y) - y0] for x, y in pixels]


def _cropped_review_context(
    row: dict[str, Any],
    group: set[tuple[int, int]],
    baseline: int,
    *,
    margin_y: int = 2,
) -> dict[str, Any]:
    """Build a vertically tight editor context without changing facit geometry.

    The stored candidate shape remains relative to the original baseline.  Only
    the UI copy of raster coordinates is shifted so the editor does not contain
    dozens of completely empty rows above and below the useful ink.
    """
    ink = [list(map(int, p)) for p in (row.get("ink") or [])]
    if not ink:
        ink = [list(p) for p in sorted(group)]

    ys = [y for _, y in ink]
    original_height = int(row.get("height") or (max(ys) + 1 if ys else 1))
    y0 = max(0, min(ys + [baseline]) - margin_y)
    y1 = min(original_height - 1, max(ys + [baseline]) + margin_y)
    if y1 < y0:
        y0 = y1 = max(0, min(original_height - 1, baseline))

    exact = []
    for match in row.get("exact") or []:
        copied = dict(match)
        copied["pixels"] = _shift_pixels(match.get("pixels") or [], y0)
        if isinstance(match.get("baseline"), int):
            copied["baseline"] = int(match["baseline"]) - y0
        exact.append(copied)

    hint = row.get("jsonl_hint") or {}
    return {
        "expected": row.get("expected"),
        "jsonl_hint": hint,
        "page_word_bbox": row.get("page_word_bbox"),
        "width": row.get("width"),
        "height": y1 - y0 + 1,
        "original_height": original_height,
        "review_y_offset": y0,
        "ink": _shift_pixels(ink, y0),
        "exact": exact,
        "candidate_pixels": _shift_pixels([list(p) for p in sorted(group)], y0),
        "baseline": baseline - y0,
    }


def collect_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_shape: dict[tuple[tuple[int, int], ...], dict[str, Any]] = {}
    seq = 0
    for row in rows:
        baseline = row.get("baseline")
        width = int(row.get("width") or 0)
        if not isinstance(baseline, int):
            continue
        groups = unknown_groups(row)
        suggestions = _jsonl_group_suggestions(row, groups)
        for group, suggestion in zip(groups, suggestions):
            # There is no way to know whether a glyph is complete when its
            # unknown raster reaches the left/right edge of the OCR crop.
            if _touches_horizontal_edge(group, width):
                continue

            shape = _shape(group, baseline)
            if not shape:
                continue
            hint = row.get("jsonl_hint") or {}
            source = {
                "expected_word": row.get("expected"),
                "jsonl_word": hint.get("text"),
                "jsonl_similarity": hint.get("similarity"),
                "page": row.get("page"),
                "subnr": row.get("subnr"),
                "source_id": (row.get("source") or {}).get("source_id"),
                "page_word_bbox": row.get("page_word_bbox"),
                "suggestion": suggestion,
            }
            cand = by_shape.get(shape)
            if cand is None:
                seq += 1
                xs = [x for x, _ in group]
                ys = [y for _, y in group]
                cand = {
                    "id": seq,
                    "shape": [list(p) for p in shape],
                    "pixels": [list(p) for p in sorted(group)],
                    "baseline": baseline,
                    "width": max(xs) - min(xs) + 1,
                    "height": max(ys) - min(ys) + 1,
                    "occurrences": 0,
                    "sources": [],
                    "suggestion_counts": {},
                    "context": _cropped_review_context(row, group, baseline),
                }
                by_shape[shape] = cand
            cand["occurrences"] += 1
            if source not in cand["sources"]:
                cand["sources"].append(source)
            if suggestion:
                counts = Counter(cand.get("suggestion_counts") or {})
                counts[suggestion] += 1
                cand["suggestion_counts"] = dict(counts)

    candidates = sorted(by_shape.values(), key=lambda c: c["id"])
    for cand in candidates:
        counts = Counter(cand.get("suggestion_counts") or {})
        if counts:
            suggestion, support = counts.most_common(1)[0]
            cand["suggestion"] = suggestion
            cand["suggestion_support"] = support
        else:
            cand["suggestion"] = ""
            cand["suggestion_support"] = 0
    return candidates


def build_html(rows: list[dict[str, Any]], facit_path: Path) -> str:
    # Keep the historical entry point working while using the current editor.
    from .ocr_editable_unknown_glyph_review import build_html as build_editable_html

    return build_editable_html(rows, facit_path)
