from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
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

    @property
    def width(self) -> int:
        return max(x for x, _ in self.pixels) + 1

    @property
    def min_y(self) -> int:
        return min(y for _, y in self.pixels)

    @property
    def max_y(self) -> int:
        return max(y for _, y in self.pixels)


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
    """Return 4-connected source-ink components and a pixel->component index."""
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
    """Return pixel-perfect placements of learned models.

    ``style`` is retained as the internal compatibility name for typography
    classification.  For facit v2 its value is the semantic ``role`` instead
    (for example ``headword-bold`` or ``unknown``).

    By default a placement must own every 4-connected source component it
    touches. Multi-row review may set ``require_whole_components=False`` so
    known exact glyphs can be peeled from one connected cross-row tangle.
    """
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
                placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
                if not placed.issubset(ink):
                    continue
                if require_whole_components and not _owns_whole_touched_components(placed, components, by_pixel):
                    continue
                out.append(
                    Match(
                        label=model.label,
                        style=model.style,
                        x=x0,
                        baseline=baseline,
                        pixels=placed,
                        model_pixels=len(model.pixels),
                        sources=model.sources,
                    )
                )
    return out


def _partition_key(matches: Iterable[Match]) -> tuple[int, int, int, int]:
    rows = list(matches)
    return (
        sum(m.model_pixels for m in rows),
        sum(m.model_pixels * m.model_pixels for m in rows),
        sum(m.sources for m in rows),
        -len(rows),
    )


def select_best_disjoint_exact(matches: Iterable[Match], *, beam_width: int = 512) -> list[Match]:
    """Choose the best pixel-disjoint set of exact glyph placements."""
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
        states = sorted(
            ((chosen, occupied) for occupied, chosen in best_by_occupied.items()),
            key=lambda state: _partition_key(state[0]),
            reverse=True,
        )[:beam_width]
    best = max(states, key=lambda state: _partition_key(state[0]))[0] if states else ()
    return sorted(best, key=lambda m: (m.x, m.baseline, m.label, m.style))


def select_best_baseline_partition(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    beam_width: int = 512,
) -> tuple[int | None, list[Match]]:
    all_matches = exact_matches(ink, width, height, models)
    if not all_matches:
        return None, []
    by_baseline: dict[int, list[Match]] = {}
    for m in all_matches:
        by_baseline.setdefault(m.baseline, []).append(m)
    best_baseline: int | None = None
    best_rows: list[Match] = []
    best_key: tuple[int, int, int, int] | None = None
    for baseline, candidates in sorted(by_baseline.items()):
        selected = select_best_disjoint_exact(candidates, beam_width=beam_width)
        key = _partition_key(selected)
        if best_key is None or key > best_key:
            best_key = key
            best_baseline = baseline
            best_rows = selected
    return best_baseline, best_rows


def select_non_overlapping_exact(matches: Iterable[Match]) -> list[Match]:
    return select_best_disjoint_exact(matches)


def exact_sequence_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: list[GlyphModel],
    expected: str,
    *,
    styles: set[str] | None = None,
) -> list[Match] | None:
    if not expected:
        return None
    candidates = exact_matches(ink, width, height, models, styles=styles)
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
            if m.x < min_anchor_x:
                continue
            if word_baseline is not None and m.baseline != word_baseline:
                continue
            if used.intersection(m.pixels):
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
    return {
        "baseline": baseline,
        "exact_candidates": len(exact_matches(ink, width, height, models)),
        "selected_exact": _rows(selected),
        "covered_pixels": len(covered),
        "source_pixels": len(ink),
        "fully_exact": covered == ink,
        "recognized": "".join(m.label for m in selected),
        "expected_word": expected,
        "fuzzy_diagnostics": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal SAOL glyph OCR: exact whole-component models, one support baseline, maximum raster coverage.")
    ap.add_argument("word_debug", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit-v2.json"))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    ink, width, height, debug = load_word_debug(args.word_debug)
    models = load_facit(args.facit)
    expected = str(debug.get("expected_word") or "")
    result = analyse(ink, width, height, models, expected=expected)
    inventory = model_inventory(models)
    expected_labels = sorted(set(expected))
    result.update({"format": "saol14-minimal-glyph-match-v10", "headword": debug.get("headword"), "page": debug.get("page"), "subnr": debug.get("subnr"), "models": len(models), "expected_label_models": {label: inventory.get(label, {}) for label in expected_labels}})
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(args.out)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
