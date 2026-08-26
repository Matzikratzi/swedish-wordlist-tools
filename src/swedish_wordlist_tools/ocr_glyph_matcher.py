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
    pixels: frozenset[tuple[int, int]]  # x normalized; y relative to baseline
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
        # Minimal matcher principle: exact large glyphs dominate by construction.
        # This score is only used to order mutually overlapping exact matches.
        return float(self.model_pixels * self.model_pixels)


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
    """Find exact glyphs, optionally constrained to one known baseline.

    First-pass use is baseline-free: a model is translated in x and baseline-y.
    A match requires all model pixels to land on source ink and no additional
    source ink inside the model's complete translated bounding box.
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


def reject_embedded_tiny(matches: Iterable[Match], ink: set[tuple[int, int]]) -> list[Match]:
    """Reject punctuation-like exact subshapes embedded in a larger ink body.

    A tiny dash can have a perfectly clean 1-row bounding box while still being
    merely a horizontal slice through a real letter.  If all pixels of such a
    candidate live in a connected source component that is substantially larger
    than the candidate, it is not an independent glyph.
    """
    out: list[Match] = []
    cache: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for m in matches:
        if m.label not in TINY_FRAGMENT_LABELS:
            out.append(m)
            continue
        comps: list[set[tuple[int, int]]] = []
        seen_ids: set[frozenset[tuple[int, int]]] = set()
        for p in m.pixels:
            comp = cache.get(p)
            if comp is None:
                comp = _component(ink, p)
                for q in comp:
                    cache[q] = comp
            key = frozenset(comp)
            if key not in seen_ids:
                seen_ids.add(key)
                comps.append(comp)
        union = set().union(*comps) if comps else set()
        if union and m.pixels.issubset(union) and len(union) >= m.model_pixels + 6:
            continue
        out.append(m)
    return out


def select_non_overlapping_exact(matches: Iterable[Match]) -> list[Match]:
    """Choose a deterministic set of exact matches, largest exact glyph first."""
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


def analyse(ink: set[tuple[int, int]], width: int, height: int, models: list[GlyphModel]) -> dict[str, Any]:
    # Pass 1: baseline-free exact discovery. Large exact glyphs vote strongly.
    exact = exact_matches(ink, width, height, models)
    seed_selected = select_non_overlapping_exact(exact)
    votes = baseline_votes(seed_selected)
    baseline = choose_baseline(seed_selected)

    # Pass 2: once baseline is known, regenerate exact candidates only on that
    # baseline and remove tiny embedded slices before final exact selection.
    if baseline is None:
        baseline_exact: list[Match] = []
        final_selected: list[Match] = []
    else:
        baseline_exact = exact_matches(ink, width, height, models, baseline_only=baseline)
        baseline_exact = reject_embedded_tiny(baseline_exact, ink)
        final_selected = select_non_overlapping_exact(baseline_exact)

    return {
        "baseline": baseline,
        "baseline_votes": dict(sorted(votes.items())),
        "exact_candidates": len(exact),
        "seed_selected_exact": _rows(seed_selected),
        "baseline_exact_candidates": len(baseline_exact),
        "selected_exact": _rows(final_selected),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal SAOL glyph matcher: exact whole-glyph matches first, baseline inferred from them.")
    ap.add_argument("word_debug", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    ink, width, height, debug = load_word_debug(args.word_debug)
    models = load_facit(args.facit)
    result = analyse(ink, width, height, models)
    result.update(
        {
            "format": "saol14-minimal-glyph-match-v2",
            "expected_word": debug.get("expected_word"),
            "headword": debug.get("headword"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "models": len(models),
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
