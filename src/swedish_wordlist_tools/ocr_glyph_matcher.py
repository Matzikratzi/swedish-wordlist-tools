from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

FACIT_FORMAT_V1 = "saol14-manual-glyph-facit-v1"
FACIT_FORMAT_V2 = "saol14-manual-glyph-facit-v2"
DEBUG_FORMAT = "saol14-word-debug-v1"


@dataclass(frozen=True)
class GlyphModel:
    label: str
    style: str
    pixels: frozenset[tuple[int, int]]
    sources: int = 0
    _width: int = field(init=False, repr=False, compare=False)
    _min_y: int = field(init=False, repr=False, compare=False)
    _max_y: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_width", max(x for x, _ in self.pixels) + 1)
        object.__setattr__(self, "_min_y", min(y for _, y in self.pixels))
        object.__setattr__(self, "_max_y", max(y for _, y in self.pixels))

    @property
    def width(self) -> int:
        return self._width

    @property
    def min_y(self) -> int:
        return self._min_y

    @property
    def max_y(self) -> int:
        return self._max_y


@dataclass(frozen=True)
class Match:
    label: str
    style: str
    x: int
    baseline: int
    pixels: frozenset[tuple[int, int]]
    model_pixels: int
    sources: int
    perfect: bool = True

    @property
    def score(self) -> float:
        return float(self.model_pixels * self.model_pixels)

    @property
    def x1(self) -> int:
        return max(x for x, _ in self.pixels)


def load_facit(path: Path) -> list[GlyphModel]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fmt = payload.get("format")
    if fmt not in {FACIT_FORMAT_V1, FACIT_FORMAT_V2}:
        raise ValueError(f"unsupported facit format: {fmt!r}")
    out: list[GlyphModel] = []
    for row in payload.get("glyphs") or []:
        pts = frozenset((int(x), int(y)) for x, y in row.get("pixels_relative_to_baseline") or [])
        if not pts:
            continue
        if fmt == FACIT_FORMAT_V2:
            role = str(row.get("role") or "unknown")
        else:
            role = str(row.get("style") or "roman")
        out.append(
            GlyphModel(
                label=str(row.get("label") or ""),
                style=role,
                pixels=pts,
                sources=len(row.get("sources") or []),
            )
        )
    return out


def load_word_debug(path: Path) -> tuple[set[tuple[int, int]], int, int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != DEBUG_FORMAT:
        raise ValueError(f"unsupported debug format: {payload.get('format')!r}")
    ink = {(int(x), int(y)) for x, y in payload.get("black_pixels") or []}
    return ink, int(payload["width"]), int(payload["height"]), payload


def _ink_components(ink: set[tuple[int, int]]) -> tuple[list[frozenset[tuple[int, int]]], dict[tuple[int, int], int]]:
    remaining = set(ink)
    components: list[frozenset[tuple[int, int]]] = []
    by_pixel: dict[tuple[int, int], int] = {}
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        comp = {seed}
        while stack:
            x, y = stack.pop()
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p in remaining:
                    remaining.remove(p)
                    comp.add(p)
                    stack.append(p)
        idx = len(components)
        frozen = frozenset(comp)
        components.append(frozen)
        for p in frozen:
            by_pixel[p] = idx
    return components, by_pixel


def _owns_whole_touched_components(
    placed: frozenset[tuple[int, int]],
    components: list[frozenset[tuple[int, int]]],
    by_pixel: dict[tuple[int, int], int],
) -> bool:
    touched = {by_pixel[p] for p in placed}
    return all(components[idx].issubset(placed) for idx in touched)


def exact_matches(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    styles: set[str] | None = None,
    baseline_only: int | None = None,
    require_whole_components: bool = True,
) -> list[Match]:
    out: list[Match] = []
    components: list[frozenset[tuple[int, int]]] = []
    by_pixel: dict[tuple[int, int], int] = {}
    if require_whole_components:
        components, by_pixel = _ink_components(ink)
    for model in models:
        if styles is not None and model.style not in styles:
            continue
        mw = model.width
        if mw > width:
            continue
        for x0 in range(0, width - mw + 1):
            b_lo = -model.min_y
            b_hi = height - 1 - model.max_y
            baselines = (baseline_only,) if baseline_only is not None else range(b_lo, b_hi + 1)
            for baseline in baselines:
                if baseline < b_lo or baseline > b_hi:
                    continue
                fits = True
                for x, y in model.pixels:
                    if (x0 + x, baseline + y) not in ink:
                        fits = False
                        break
                if not fits:
                    continue
                placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
                if require_whole_components and not _owns_whole_touched_components(placed, components, by_pixel):
                    continue
                out.append(Match(label=model.label, style=model.style, x=x0, baseline=baseline, pixels=placed, model_pixels=len(model.pixels), sources=model.sources))
    return out


def _partition_key(matches: Iterable[Match]) -> tuple[int, int, int, int]:
    rows = list(matches)
    return (sum(m.model_pixels for m in rows), sum(m.model_pixels * m.model_pixels for m in rows), sum(m.sources for m in rows), -len(rows))


def select_best_disjoint_exact(matches: Iterable[Match], *, beam_width: int = 512) -> list[Match]:
    rows = sorted(matches, key=lambda m: (-m.model_pixels, -m.score, -m.sources, m.x, m.label, m.style))
    states: list[tuple[tuple[Match, ...], frozenset[tuple[int, int]]]] = [((), frozenset())]
    for m in rows:
        expanded = list(states)
        for chosen, occupied in states:
            if occupied.intersection(m.pixels):
                continue
            expanded.append((chosen + (m,), frozenset(set(occupied) | set(m.pixels))))
        best_by_occupied: dict[frozenset[tuple[int, int]], tuple[Match, ...]] = {}
        for chosen, occupied in expanded:
            previous = best_by_occupied.get(occupied)
            if previous is None or _partition_key(chosen) > _partition_key(previous):
                best_by_occupied[occupied] = chosen
        states = sorted(((chosen, occupied) for occupied, chosen in best_by_occupied.items()), key=lambda state: _partition_key(state[0]), reverse=True)[:beam_width]
    best = max(states, key=lambda state: _partition_key(state[0]))[0] if states else ()
    return sorted(best, key=lambda m: (m.x, m.baseline, m.label, m.style))


def _component_partition_key(chosen: Iterable[Match], occupied: frozenset[tuple[int, int]], components: Iterable[frozenset[tuple[int, int]]]) -> tuple[int, int, int, int, int]:
    rows = list(chosen)
    complete_pixels = sum(len(component) for component in components if component.issubset(occupied))
    normal = _partition_key(rows)
    return (complete_pixels, *normal)


def select_best_disjoint_exact_for_ink(matches: Iterable[Match], ink: set[tuple[int, int]], *, beam_width: int = 512) -> list[Match]:
    rows = sorted(matches, key=lambda m: (-m.model_pixels, -m.score, -m.sources, m.x, m.label, m.style))
    components, _by_pixel = _ink_components(ink)
    states: list[tuple[tuple[Match, ...], frozenset[tuple[int, int]]]] = [((), frozenset())]
    for match in rows:
        expanded = list(states)
        for chosen, occupied in states:
            if occupied.intersection(match.pixels):
                continue
            expanded.append((chosen + (match,), frozenset(set(occupied) | set(match.pixels))))
        best_by_occupied: dict[frozenset[tuple[int, int]], tuple[Match, ...]] = {}
        for chosen, occupied in expanded:
            previous = best_by_occupied.get(occupied)
            if previous is None or _component_partition_key(chosen, occupied, components) > _component_partition_key(previous, occupied, components):
                best_by_occupied[occupied] = chosen
        states = sorted(((chosen, occupied) for occupied, chosen in best_by_occupied.items()), key=lambda state: _component_partition_key(state[0], state[1], components), reverse=True)[:beam_width]
    best = max(states, key=lambda state: _component_partition_key(state[0], state[1], components))[0] if states else ()
    return sorted(best, key=lambda m: (m.x, m.baseline, m.label, m.style))


def select_best_baseline_partition(ink: set[tuple[int, int]], width: int, height: int, models: Iterable[GlyphModel], *, beam_width: int = 512) -> tuple[int | None, list[Match]]:
    all_matches = exact_matches(ink, width, height, models, require_whole_components=False)
    if not all_matches:
        return None, []
    by_baseline: dict[int, list[Match]] = {}
    for m in all_matches:
        by_baseline.setdefault(m.baseline, []).append(m)
    best_baseline: int | None = None
    best_rows: list[Match] = []
    best_key: tuple[int, int, int, int, int] | None = None
    components, _by_pixel = _ink_components(ink)
    for baseline, candidates in sorted(by_baseline.items()):
        selected = select_best_disjoint_exact_for_ink(candidates, ink, beam_width=beam_width)
        occupied = frozenset().union(*(match.pixels for match in selected)) if selected else frozenset()
        key = _component_partition_key(selected, occupied, components)
        if best_key is None or key > best_key:
            best_key = key
            best_baseline = baseline
            best_rows = selected
    return best_baseline, best_rows


def select_non_overlapping_exact(matches: Iterable[Match]) -> list[Match]:
    return select_best_disjoint_exact(matches)


def exact_sequence_cover(ink: set[tuple[int, int]], width: int, height: int, models: list[GlyphModel], expected: str, *, styles: set[str] | None = None) -> list[Match] | None:
    if not expected:
        return None
    candidates = exact_matches(ink, width, height, models, styles=styles, require_whole_components=False)
    by_pos: dict[int, list[Match]] = {i: [] for i in range(len(expected))}
    for m in candidates:
        for pos in range(len(expected)):
            if expected.startswith(m.label, pos):
                by_pos[pos].append(m)
    for rows in by_pos.values():
        rows.sort(key=lambda m: (m.x, -len(m.label), -m.model_pixels, -m.sources, m.baseline, m.style))
    target = frozenset(ink)
    seen: set[tuple[int, int, int | None, frozenset[tuple[int, int]]]] = set()
    def dfs(pos: int, min_anchor_x: int, word_baseline: int | None, used: frozenset[tuple[int, int]]) -> list[Match] | None:
        state = (pos, min_anchor_x, word_baseline, used)
        if state in seen:
            return None
        seen.add(state)
        if pos == len(expected):
            return [] if used == target else None
        for m in by_pos.get(pos, []):
            if m.x < min_anchor_x or (word_baseline is not None and m.baseline != word_baseline) or used.intersection(m.pixels):
                continue
            new_used = frozenset(set(used) | set(m.pixels))
            baseline = m.baseline if word_baseline is None else word_baseline
            tail = dfs(pos + len(m.label), m.x + 1, baseline, new_used)
            if tail is not None:
                return [m] + tail
        return None
    return dfs(0, 0, None, frozenset())


def baseline_votes(matches: Iterable[Match]) -> Counter[int]:
    votes: Counter[int] = Counter()
    for m in matches:
        votes[m.baseline] += m.model_pixels
    return votes


def choose_baseline(matches: Iterable[Match]) -> int | None:
    votes = baseline_votes(matches)
    if not votes:
        return None
    return min(votes, key=lambda y: (-votes[y], y))


def _rows(matches: Iterable[Match]) -> list[dict[str, Any]]:
    return [{"label": m.label, "style": m.style, "x": m.x, "baseline": m.baseline, "pixels": m.model_pixels, "sources": m.sources, "score": m.score} for m in matches]


def model_inventory(models: Iterable[GlyphModel]) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = {}
    for m in models:
        out.setdefault(m.label, Counter())[m.style] += 1
    return {label: dict(sorted(styles.items())) for label, styles in sorted(out.items())}


def analyse(ink: set[tuple[int, int]], width: int, height: int, models: list[GlyphModel], expected: str | None = None) -> dict[str, Any]:
    baseline, selected = select_best_baseline_partition(ink, width, height, models)
    covered = set().union(*(m.pixels for m in selected)) if selected else set()
    sequence = exact_sequence_cover(ink, width, height, models, expected) if expected else None
    return {"baseline": baseline, "exact_candidates": len(exact_matches(ink, width, height, models, require_whole_components=False)), "selected_exact": _rows(selected), "covered_pixels": len(covered), "source_pixels": len(ink), "fully_exact": covered == ink, "recognized": "".join(m.label for m in selected), "sequence_exact": _rows(sequence) if sequence else None, "sequence_recognized": "".join(m.label for m in sequence) if sequence else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("debug_json")
    ap.add_argument("--facit", required=True)
    ap.add_argument("--expected")
    args = ap.parse_args(argv)
    ink, width, height, _payload = load_word_debug(Path(args.debug_json))
    models = load_facit(Path(args.facit))
    payload = analyse(ink, width, height, models, expected=args.expected)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["fully_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
