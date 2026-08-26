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


def exact_matches(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    styles: set[str] | None = None,
) -> list[Match]:
    """Find exact glyphs without knowing the baseline in advance.

    A model is translated in x and baseline-y.  It is exact only when every
    model pixel lands on source ink *and* its complete translated bounding box
    contains no additional source ink.  Thus a small dash embedded inside a q
    is not an exact whole-glyph match even though all dash pixels are black.
    """
    out: list[Match] = []
    for model in models:
        if styles is not None and model.style not in styles:
            continue
        mw = model.width
        if mw > width:
            continue
        for x0 in range(0, width - mw + 1):
            # baseline may be outside the raster only if the translated model
            # still fits; these bounds are the exact valid range.
            b_lo = -model.min_y
            b_hi = height - 1 - model.max_y
            for baseline in range(b_lo, b_hi + 1):
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
    """Choose a deterministic set of exact matches, largest exact glyph first.

    This is intentionally simple.  Since every candidate is already an exact
    whole-bounding-box match, a larger exact glyph dominates any exact fragment
    that overlaps it.  Approximate matches are a later stage and are not part of
    this selector.
    """
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
        # Exact glyph area is evidence strength. A full 41-pixel q therefore
        # outweighs any tiny punctuation that somehow survives as an independent
        # exact glyph elsewhere.
        votes[m.baseline] += m.model_pixels
    return votes


def choose_baseline(matches: Iterable[Match]) -> int | None:
    votes = baseline_votes(matches)
    if not votes:
        return None
    return min(votes, key=lambda y: (-votes[y], y))


def analyse(ink: set[tuple[int, int]], width: int, height: int, models: list[GlyphModel]) -> dict[str, Any]:
    exact = exact_matches(ink, width, height, models)
    selected = select_non_overlapping_exact(exact)
    votes = baseline_votes(selected)
    baseline = choose_baseline(selected)
    return {
        "baseline": baseline,
        "baseline_votes": dict(sorted(votes.items())),
        "exact_candidates": len(exact),
        "selected_exact": [
            {
                "label": m.label,
                "style": m.style,
                "x": m.x,
                "baseline": m.baseline,
                "pixels": m.model_pixels,
                "sources": m.sources,
                "score": m.score,
            }
            for m in selected
        ],
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
            "format": "saol14-minimal-glyph-match-v1",
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
