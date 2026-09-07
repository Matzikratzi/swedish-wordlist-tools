from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v5 as v5
from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_exact_glyph_review_queue_v6 import build_html as build_html_v6
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, Match, load_facit, load_word_debug, select_best_baseline_partition


@dataclass(frozen=True)
class DetachedProfile:
    label: str
    style: str
    side: str  # top / bottom
    min_x: int
    max_x: int
    min_y: int
    max_y: int


def _components(points: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> list[set[tuple[int, int]]]:
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


def _span_x(points: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in points]
    return min(xs), max(xs)


def _overlap_x(a: set[tuple[int, int]] | frozenset[tuple[int, int]], b: set[tuple[int, int]] | frozenset[tuple[int, int]]) -> bool:
    a0, a1 = _span_x(a)
    b0, b1 = _span_x(b)
    return max(a0, b0) <= min(a1, b1)


def _model_body_and_detached(model: GlyphModel) -> tuple[set[tuple[int, int]], list[set[tuple[int, int]]]]:
    comps = _components(model.pixels)
    # The body is the largest component that reaches closest to the baseline.
    # This naturally leaves i-dots, rings, trema, accents etc. detached.
    body = max(comps, key=lambda c: (len(c), -min(abs(y) for _, y in c)))
    detached = [c for c in comps if c is not body]
    return body, detached


def _learn_geometry(models: list[GlyphModel], style: str) -> tuple[int, int, list[DetachedProfile]]:
    rows = [m for m in models if m.style == style] or list(models)
    if not rows:
        return 0, 0, []

    body_above = 0
    body_below = 0
    profiles: list[DetachedProfile] = []
    for model in rows:
        body, detached = _model_body_and_detached(model)
        body_above = max(body_above, max(0, -min(y for _, y in body)))
        body_below = max(body_below, max(0, max(y for _, y in body)))
        for comp in detached:
            xs = [x for x, _ in comp]
            ys = [y for _, y in comp]
            if max(ys) < -body_above:
                side = "top"
            elif min(ys) > body_below:
                side = "bottom"
            else:
                # Detached components inside the ordinary body band (e.g. a dot
                # close to a stem) are not useful for neighboring-row trimming.
                continue
            profiles.append(
                DetachedProfile(
                    label=model.label,
                    style=model.style,
                    side=side,
                    min_x=min(xs),
                    max_x=max(xs),
                    min_y=min(ys),
                    max_y=max(ys),
                )
            )
    return body_above, body_below, profiles


def _profile_fits_source_component(
    comp: set[tuple[int, int]],
    baseline: int,
    profile: DetachedProfile,
    *,
    anchor_x: int | None = None,
    tolerance: int = 1,
) -> bool:
    xs = [x for x, _ in comp]
    ys = [y - baseline for _, y in comp]
    if min(ys) < profile.min_y - tolerance or max(ys) > profile.max_y + tolerance:
        return False
    if anchor_x is None:
        # Unknown body: vertical geometry is the strong discriminator; require
        # approximately the same detached-component width as a learned example.
        return abs((max(xs) - min(xs)) - (profile.max_x - profile.min_x)) <= tolerance
    rel_min = min(xs) - anchor_x
    rel_max = max(xs) - anchor_x
    return rel_min >= profile.min_x - tolerance and rel_max <= profile.max_x + tolerance


def _trim_neighbor_noise(
    ink: set[tuple[int, int]],
    baseline: int,
    models: list[GlyphModel],
    style: str,
    seed_matches: list[Match],
) -> tuple[set[tuple[int, int]], set[tuple[int, int]], tuple[int, int], list[DetachedProfile]]:
    body_above, body_below, profiles = _learn_geometry(models, style)
    y0 = baseline - body_above
    y1 = baseline + body_below
    comps = _components(ink)
    main = [c for c in comps if any(y0 <= y <= y1 for _, y in c)]
    protected_pixels = set().union(*(m.pixels for m in seed_matches)) if seed_matches else set()

    by_style_label: dict[tuple[str, str], list[DetachedProfile]] = {}
    for p in profiles:
        by_style_label.setdefault((p.style, p.label), []).append(p)

    kept: set[tuple[int, int]] = set()
    removed: set[tuple[int, int]] = set()
    for comp in comps:
        if comp in main or comp & protected_pixels:
            kept.update(comp)
            continue

        comp_side = "top" if max(y for _, y in comp) < y0 else ("bottom" if min(y for _, y in comp) > y1 else "middle")
        if comp_side == "middle":
            kept.update(comp)
            continue

        # If a known exact glyph occupies the x-range, only detached geometry
        # learned for that exact label/style may justify this component.
        aligned_matches = [m for m in seed_matches if _overlap_x(comp, m.pixels)]
        if aligned_matches:
            allowed = False
            for m in aligned_matches:
                for p in by_style_label.get((m.style, m.label), []):
                    if p.side == comp_side and _profile_fits_source_component(comp, baseline, p, anchor_x=m.x):
                        allowed = True
                        break
                if allowed:
                    break
            if allowed:
                kept.update(comp)
            else:
                removed.update(comp)
            continue

        # Unknown body below/above: keep only when the loose component both lines
        # up with main-line ink and resembles a detached component geometry that
        # actually exists in the learned typeface/style.
        aligned_main = any(_overlap_x(comp, m) for m in main)
        fits_any = any(p.side == comp_side and _profile_fits_source_component(comp, baseline, p) for p in profiles)
        if aligned_main and fits_any:
            kept.update(comp)
        else:
            removed.update(comp)

    return kept, removed, (body_above, body_below), profiles


def _analyse_one(path: Path, models: list[GlyphModel]):
    raw_ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    style = str(debug.get("style") or (debug.get("card_dataset") or {}).get("style") or "bold")

    baseline0, seed = select_best_baseline_partition(raw_ink, width, height, models)
    if baseline0 is None:
        baseline0 = _raw_baseline_guess(raw_ink, height)
    if baseline0 is None:
        cleaned = set(raw_ink)
        removed: set[tuple[int, int]] = set()
        ext = (0, 0)
        profiles: list[DetachedProfile] = []
    else:
        cleaned, removed, ext, profiles = _trim_neighbor_noise(raw_ink, baseline0, models, style, seed)

    baseline, shown = select_best_baseline_partition(cleaned, width, height, models)
    if baseline is None:
        baseline = baseline0
        source = "raw-density-manual-seed"
    else:
        source = "max-exact-raster-coverage"
    if removed:
        source += f"+trim-learned-diacritic-geometry({len(removed)})"

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    return {
        "expected": expected,
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": style,
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in cleaned]),
        "raw_ink": sorted([list(p) for p in raw_ink]),
        "removed_noise": sorted([list(p) for p in removed]),
        "normal_extents": {"above": ext[0], "below": ext[1]},
        "learned_detached_profiles": len(profiles),
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": covered == cleaned,
        "exact": [
            {
                "label": m.label,
                "style": m.style,
                "x": m.x,
                "baseline": m.baseline,
                "pixels": sorted([list(p) for p in m.pixels]),
            }
            for m in shown
        ],
        "unexplained": sorted([list(p) for p in cleaned - covered]),
        "recognized": "".join(m.label for m in shown),
        "source": {
            "expected_word": debug.get("expected_word"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "source_id": (debug.get("card_dataset") or {}).get("sourceId") or debug.get("source_id") or "",
            "word_file": (debug.get("card_dataset") or {}).get("wordFile") or debug.get("word_file") or "",
        },
    }


def build_html(paths: list[Path], facit_path: Path) -> str:
    original = v5._analyse_one
    v5._analyse_one = _analyse_one
    try:
        return build_html_v6(paths, facit_path)
    finally:
        v5._analyse_one = original


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster OCR review with learned detached-diacritic geometry trimming.")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--facit-html", type=Path, default=Path("/tmp/glyph-facit-table.html"))
    args = ap.parse_args()
    files = _expand_inputs(args.inputs)
    if not files:
        raise SystemExit("no word-debug JSON files found")
    args.out.write_text(build_html(files, args.facit), encoding="utf-8")
    args.facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")
    print(f"debug_files={len(files)}")
    print(args.out)
    print(f"facit_html={args.facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
