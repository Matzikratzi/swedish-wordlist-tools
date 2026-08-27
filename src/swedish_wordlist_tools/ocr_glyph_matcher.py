from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FACIT_FORMAT = "saol14-manual-glyph-facit-v1"
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


def exact_matches(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    styles: set[str] | None = None,
    baseline_only: int | None = None,
) -> list[Match]:
    """Return pixel-perfect placements of learned glyph models.

    A model is exact when every one of its pixels lands on source ink.  Other
    source pixels may exist inside the same x span: neighbouring glyphs can
    overlap horizontally (especially italic glyphs) without sharing actual
    black pixels.  Pixel ownership is resolved later when matches are combined.
    """
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
    *,
    styles: set[str] | None = None,
) -> list[Match] | None:
    """Return an exact ordered cover whose labels concatenate to expected.

    Every selected glyph must imply the same support baseline for the whole word.
    Multi-character models such as ``tt`` are valid alternatives to separate
    ``t`` + ``t`` models.  Horizontal bounding boxes may overlap, but selected
    glyphs may never share an actual source pixel.
    """
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

    def dfs(
        pos: int,
        min_anchor_x: int,
        word_baseline: int | None,
        used: frozenset[tuple[int, int]],
    ) -> list[Match] | None:
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
            # Do not jump past wholly unexplained ink.  X-overlap is allowed, so
            # ordering follows glyph anchors rather than right bounding edges.
            left_unexplained = any(x < m.x and (x, y) not in used for x, y in ink)
            if left_unexplained:
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
    ap = argparse.ArgumentParser(description="Minimal SAOL glyph matcher: exact glyphs only; one support baseline per word.")
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
            "format": "saol14-minimal-glyph-match-v8",
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
