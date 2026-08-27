from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FACIT_FORMAT = "saol14-manual-glyph-facit-v1"
DEBUG_FORMAT = "saol14-word-debug-v1"
TINY_FRAGMENT_LABELS = frozenset({".", "·", "-", ",", "¤", "|"})


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
    if payload.get("format") != FACIT_FORMAT:
        raise ValueError(f"unsupported facit format: {payload.get('format')!r}")
    out: list[GlyphModel] = []
    for row in payload.get("glyphs") or []:
        pts = frozenset((int(x), int(y)) for x, y in row.get("pixels_relative_to_baseline") or [])
        if not pts:
            continue
        out.append(
            GlyphModel(
                label=str(row.get("label") or ""),
                style=str(row.get("style") or "roman"),
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


def _bbox_pixels(ink: set[tuple[int, int]], x0: int, x1: int, y0: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x, y in ink if x0 <= x <= x1 and y0 <= y <= y1}


def _component(ink: set[tuple[int, int]], start: tuple[int, int]) -> set[tuple[int, int]]:
    if start not in ink:
        return set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if q in ink and q not in seen:
                seen.add(q)
                stack.append(q)
    return seen


def exact_matches(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    styles: set[str] | None = None,
    baseline_only: int | None = None,
) -> list[Match]:
    out: list[Match] = []
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
                y0 = baseline + model.min_y
                y1 = baseline + model.max_y
                box = _bbox_pixels(ink, x0, x0 + mw - 1, y0, y1)
                if box != set(placed):
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


def select_non_overlapping_exact(matches: Iterable[Match]) -> list[Match]:
    ranked = sorted(
        matches,
        key=lambda m: (-m.score, -m.model_pixels, -m.sources, m.x, m.baseline, m.label, m.style),
    )
    occupied: set[tuple[int, int]] = set()
    chosen: list[Match] = []
    for m in ranked:
        if occupied.intersection(m.pixels):
            continue
        chosen.append(m)
        occupied.update(m.pixels)
    return sorted(chosen, key=lambda m: (m.x, m.baseline, m.label, m.style))


def exact_sequence_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: list[GlyphModel],
    expected: str,
) -> list[Match] | None:
    """Return an exact left-to-right cover whose labels concatenate to expected.

    Baseline is deliberately local to each glyph. A later part of a word may be
    shifted vertically and still be an exact cover. Multi-character models such
    as ``tt`` are valid alternatives to separate ``t`` + ``t`` models.
    """
    if not expected:
        return None
    candidates = exact_matches(ink, width, height, models)
    by_pos: dict[int, list[Match]] = {i: [] for i in range(len(expected))}
    for m in candidates:
        for pos in range(len(expected)):
            if expected.startswith(m.label, pos):
                by_pos[pos].append(m)
    for rows in by_pos.values():
        rows.sort(key=lambda m: (m.x, -len(m.label), -m.model_pixels, -m.sources, m.baseline, m.style))

    target = frozenset(ink)
    seen: set[tuple[int, int, frozenset[tuple[int, int]]]] = set()

    def dfs(pos: int, min_x: int, used: frozenset[tuple[int, int]]) -> list[Match] | None:
        state = (pos, min_x, used)
        if state in seen:
            return None
        seen.add(state)
        if pos == len(expected):
            return [] if used == target else None
        for m in by_pos.get(pos, []):
            if m.x < min_x:
                continue
            if used.intersection(m.pixels):
                continue
            # Do not skip unexplained ink to the left of the next candidate.
            left_unexplained = any(x < m.x and (x, y) not in used for x, y in ink)
            if left_unexplained:
                continue
            new_used = frozenset(set(used) | set(m.pixels))
            tail = dfs(pos + len(m.label), m.x1 + 1, new_used)
            if tail is not None:
                return [m] + tail
        return None

    return dfs(0, 0, frozenset())


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
    return [
        {
            "label": m.label,
            "style": m.style,
            "x": m.x,
            "baseline": m.baseline,
            "pixels": m.model_pixels,
            "sources": m.sources,
            "score": m.score,
        }
        for m in matches
    ]


def model_inventory(models: Iterable[GlyphModel]) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = {}
    for m in models:
        out.setdefault(m.label, Counter())[m.style] += 1
    return {label: dict(sorted(styles.items())) for label, styles in sorted(out.items())}


def analyse(ink: set[tuple[int, int]], width: int, height: int, models: list[GlyphModel], expected: str | None = None) -> dict[str, Any]:
    exact = exact_matches(ink, width, height, models)
    seed_selected = select_non_overlapping_exact(exact)
    votes = baseline_votes(seed_selected)
    baseline = choose_baseline(seed_selected)
    cover = exact_sequence_cover(ink, width, height, models, expected) if expected else None
    return {
        "baseline": baseline,
        "baseline_votes": dict(sorted(votes.items())),
        "exact_candidates": len(exact),
        "seed_selected_exact": _rows(seed_selected),
        "exact_sequence_cover": _rows(cover or []),
        "fully_exact": cover is not None,
        "selected_exact": _rows(cover or seed_selected),
        "fuzzy_diagnostics": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal SAOL glyph matcher: exact glyphs only; local baselines allowed.")
    ap.add_argument("word_debug", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    ink, width, height, debug = load_word_debug(args.word_debug)
    models = load_facit(args.facit)
    expected = str(debug.get("expected_word") or "")
    result = analyse(ink, width, height, models, expected=expected)
    inventory = model_inventory(models)
    expected_labels = sorted(set(expected))
    result.update(
        {
            "format": "saol14-minimal-glyph-match-v4",
            "expected_word": debug.get("expected_word"),
            "headword": debug.get("headword"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "models": len(models),
            "expected_label_models": {label: inventory.get(label, {}) for label in expected_labels},
        }
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(args.out)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
