from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


@dataclass(frozen=True)
class Template:
    style: str
    label: str
    pixels: tuple[tuple[int, int], ...]
    width: int
    height: int
    baseline_offset: int
    source_id: str
    subnr: str


def _ink_pixels(path: Path, threshold: int) -> tuple[set[tuple[int, int]], int, int]:
    with Image.open(path) as im0:
        im = im0.convert("L")
        width, height = im.size
        ink = {
            (x, y)
            for y in range(height)
            for x in range(width)
            if im.getpixel((x, y)) < threshold
        }
    return ink, width, height


def _guess_baseline(path: Path, threshold: int = 210) -> tuple[int, float]:
    """Estimate the row ordinary letters stand on.

    This mirrors the hybrid review editor's baseline estimator, including the
    empirically observed +1 correction.  The returned y is the last ink row
    above the baseline edge.
    """
    with Image.open(path) as im0:
        im = im0.convert("L")
        lows: list[int] = []
        for x in range(im.width):
            ys = [y for y in range(im.height) if im.getpixel((x, y)) < threshold]
            if ys:
                lows.append(max(ys))
        if not lows:
            return max(0, im.height - 2), 0.0
        counts = Counter(lows)
        scores = {
            y: counts.get(y - 1, 0) + 2 * counts.get(y, 0) + counts.get(y + 1, 0)
            for y in range(im.height)
        }
        best = max(scores.values())
        candidates = [y for y, score in scores.items() if score >= best * 0.92]
        raw = min(candidates) if candidates else max(scores, key=scores.get)
        baseline = min(im.height - 1, raw + 1)
        confidence = counts.get(raw, 0) / max(1, len(lows))
        return baseline, confidence


def _split_by_large_x_gap(
    points: list[tuple[int, int]], *, split_gap: int
) -> list[list[tuple[int, int]]]:
    """Split repeated occurrences accidentally stored under one label.

    The editor stores a label as one set per word. If the same glyph was marked
    twice (e.g. two 'a' occurrences), they can therefore appear as one annotation.
    We split only across a conspicuously empty horizontal gap. Detached accents
    and i/j dots remain with their glyph because they share the same x support.
    """
    if not points:
        return []
    xs = sorted({x for x, _ in points})
    cuts: list[tuple[int, int]] = []
    start = xs[0]
    prev = xs[0]
    for x in xs[1:]:
        if x - prev - 1 >= split_gap:
            cuts.append((start, prev))
            start = x
        prev = x
    cuts.append((start, prev))
    if len(cuts) == 1:
        return [points]
    return [
        [(x, y) for x, y in points if lo <= x <= hi]
        for lo, hi in cuts
        if any(lo <= x <= hi for x, _ in points)
    ]


def _normalize_occurrence(
    *,
    style: str,
    label: str,
    points: list[tuple[int, int]],
    baseline: int,
    source_id: str,
    subnr: str,
) -> Template:
    xmin = min(x for x, _ in points)
    ymin = min(y for _, y in points)
    norm = tuple(sorted((x - xmin, y - ymin) for x, y in points))
    width = max(x for x, _ in norm) + 1
    height = max(y for _, y in norm) + 1
    return Template(
        style=style,
        label=label,
        pixels=norm,
        width=width,
        height=height,
        baseline_offset=baseline - ymin,
        source_id=source_id,
        subnr=subnr,
    )


def _load_templates(atlas: Path, split_gap: int) -> list[Template]:
    payload = json.loads(atlas.read_text(encoding="utf-8"))
    out: list[Template] = []
    for word in payload.get("words", []):
        if not isinstance(word, dict):
            continue
        style = str(word.get("style") or "")
        source_id = str(word.get("source_id") or "")
        subnr = str(word.get("subnr") or "")
        baseline = int(word.get("baseline_y", 0))
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            label = str(ann.get("label") or "")
            raw = ann.get("pixels")
            if not label or not isinstance(raw, list):
                continue
            points = [
                (int(p[0]), int(p[1]))
                for p in raw
                if isinstance(p, list) and len(p) == 2
            ]
            for occurrence in _split_by_large_x_gap(points, split_gap=split_gap):
                if occurrence:
                    out.append(
                        _normalize_occurrence(
                            style=style,
                            label=label,
                            points=occurrence,
                            baseline=baseline,
                            source_id=source_id,
                            subnr=subnr,
                        )
                    )
    return out


def _template_models(templates: Iterable[Template]) -> dict[str, dict[str, list[dict[str, object]]]]:
    """Deduplicate templates while preserving independent-source counts."""
    grouped: dict[tuple[str, str, tuple[tuple[int, int], ...], int], set[tuple[str, str]]] = defaultdict(set)
    geom: dict[tuple[str, str, tuple[tuple[int, int], ...], int], tuple[int, int]] = {}
    for t in templates:
        key = (t.style, t.label, t.pixels, t.baseline_offset)
        grouped[key].add((t.source_id, t.subnr))
        geom[key] = (t.width, t.height)

    out: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    for (style, label, pixels, baseline_offset), sources in grouped.items():
        width, height = geom[(style, label, pixels, baseline_offset)]
        out[style][label].append(
            {
                "pixels": pixels,
                "width": width,
                "height": height,
                "baseline_offset": baseline_offset,
                "source_count": len(sources),
                "sources": sources,
            }
        )
    return {style: dict(labels) for style, labels in out.items()}


def _score_at(
    *,
    ink: set[tuple[int, int]],
    x0: int,
    y0: int,
    model: dict[str, object],
) -> tuple[int, int, float]:
    pixels = model["pixels"]
    assert isinstance(pixels, tuple)
    transformed = {(x0 + x, y0 + y) for x, y in pixels}
    missing = len(transformed - ink)

    width = int(model["width"])
    height = int(model["height"])
    inside = {
        (x, y)
        for x, y in ink
        if x0 <= x < x0 + width and y0 <= y < y0 + height
    }
    extra = len(inside - transformed)
    # Missing template ink is much more serious than unrelated neighboring ink.
    score = missing + 0.20 * extra
    return missing, extra, score


def _scan_model(
    *,
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    baseline: int,
    model: dict[str, object],
    baseline_tolerance: int,
    max_missing: int,
    max_extra: int,
) -> list[dict[str, object]]:
    mw = int(model["width"])
    mh = int(model["height"])
    bo = int(model["baseline_offset"])
    if mw > width or mh > height:
        return []

    hits: list[dict[str, object]] = []
    ideal_y0 = baseline - bo
    for dy in range(-baseline_tolerance, baseline_tolerance + 1):
        y0 = ideal_y0 + dy
        if y0 < 0 or y0 + mh > height:
            continue
        for x0 in range(0, width - mw + 1):
            missing, extra, score = _score_at(ink=ink, x0=x0, y0=y0, model=model)
            if missing <= max_missing and extra <= max_extra:
                hits.append(
                    {
                        "x": x0,
                        "y": y0,
                        "width": mw,
                        "height": mh,
                        "baseline_dy": dy,
                        "missing": missing,
                        "extra": extra,
                        "score": round(score, 4),
                        "exact_ink": missing == 0,
                        "template_source_count": int(model["source_count"]),
                    }
                )
    hits.sort(key=lambda h: (float(h["score"]), abs(int(h["baseline_dy"])), int(h["x"])))
    return hits


def _nonoverlap(hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    chosen: list[dict[str, object]] = []
    occupied: list[tuple[int, int, int, int]] = []
    for hit in hits:
        x0, y0 = int(hit["x"]), int(hit["y"])
        x1, y1 = x0 + int(hit["width"]), y0 + int(hit["height"])
        overlaps = False
        for ax0, ay0, ax1, ay1 in occupied:
            ix = max(0, min(x1, ax1) - max(x0, ax0))
            iy = max(0, min(y1, ay1) - max(y0, ay0))
            inter = ix * iy
            area = min((x1 - x0) * (y1 - y0), (ax1 - ax0) * (ay1 - ay0))
            if area and inter / area > 0.55:
                overlaps = True
                break
        if overlaps:
            continue
        chosen.append(hit)
        occupied.append((x0, y0, x1, y1))
        if len(chosen) >= limit:
            break
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find manually annotated raster glyph/cluster forms in other word crops."
    )
    ap.add_argument("atlas", type=Path, help="Manual pixel atlas JSON (v1/v3 compatible)")
    ap.add_argument("library", type=Path, help="Mixed-style word-segment library")
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--limit", type=int, default=100, help="Maximum target words")
    ap.add_argument("--ink-threshold", type=int, default=210)
    ap.add_argument("--baseline-tolerance", type=int, default=1)
    ap.add_argument("--max-missing", type=int, default=0, help="Allowed missing template pixels")
    ap.add_argument("--max-extra", type=int, default=4, help="Allowed extra ink pixels inside template bbox")
    ap.add_argument("--split-gap", type=int, default=5, help="Empty x columns that split repeated same-label occurrences")
    ap.add_argument("--hits-per-label", type=int, default=4)
    ap.add_argument(
        "--include-reference-words",
        action="store_true",
        help="Also scan words that contributed atlas annotations (default excludes them)",
    )
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")

    templates = _load_templates(args.atlas, split_gap=args.split_gap)
    models = _template_models(templates)
    reference_source_ids = {t.source_id for t in templates if t.source_id}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    words = [w for w in manifest.get("words", []) if isinstance(w, dict)]
    if args.style:
        words = [w for w in words if str(w.get("style") or "") == args.style]
    if not args.include_reference_words:
        words = [w for w in words if str(w.get("source_id") or "") not in reference_source_ids]
    if args.limit > 0:
        words = words[: args.limit]

    results: list[dict[str, object]] = []
    label_hit_words: Counter[tuple[str, str]] = Counter()
    exact_hit_words: Counter[tuple[str, str]] = Counter()

    for word in words:
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not rel or not path.exists():
            continue
        style = str(word.get("style") or "")
        style_models = models.get(style, {})
        if not style_models:
            continue
        ink, width, height = _ink_pixels(path, args.ink_threshold)
        baseline, baseline_confidence = _guess_baseline(path, args.ink_threshold)
        matches: dict[str, list[dict[str, object]]] = {}
        for label, label_models in style_models.items():
            all_hits: list[dict[str, object]] = []
            for model_index, model in enumerate(label_models):
                for hit in _scan_model(
                    ink=ink,
                    width=width,
                    height=height,
                    baseline=baseline,
                    model=model,
                    baseline_tolerance=args.baseline_tolerance,
                    max_missing=args.max_missing,
                    max_extra=args.max_extra,
                ):
                    hit = dict(hit)
                    hit["model_index"] = model_index
                    all_hits.append(hit)
            all_hits.sort(
                key=lambda h: (
                    float(h["score"]),
                    -int(h["template_source_count"]),
                    abs(int(h["baseline_dy"])),
                    int(h["x"]),
                )
            )
            chosen = _nonoverlap(all_hits, args.hits_per_label)
            if chosen:
                matches[label] = chosen
                label_hit_words[(style, label)] += 1
                if any(bool(h["exact_ink"]) and int(h["extra"]) == 0 for h in chosen):
                    exact_hit_words[(style, label)] += 1

        if matches:
            results.append(
                {
                    "source_id": str(word.get("source_id") or ""),
                    "subnr": str(word.get("subnr") or ""),
                    "page": word.get("page"),
                    "style": style,
                    "expected_word": str(word.get("expected_word") or ""),
                    "headword": str(word.get("headword") or ""),
                    "word_file": rel,
                    "width": width,
                    "height": height,
                    "baseline_y": baseline,
                    "baseline_confidence": round(baseline_confidence, 4),
                    "matches": matches,
                }
            )

    model_summary: dict[str, dict[str, list[dict[str, object]]]] = {}
    for style, labels in models.items():
        model_summary[style] = {}
        for label, label_models in labels.items():
            model_summary[style][label] = [
                {
                    "width": int(m["width"]),
                    "height": int(m["height"]),
                    "baseline_offset": int(m["baseline_offset"]),
                    "pixel_count": len(m["pixels"]),
                    "source_count": int(m["source_count"]),
                }
                for m in label_models
            ]

    summary = {
        "format": "saol-manual-pixel-atlas-match-v1",
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": sum(len(v) for labels in models.values() for v in labels.values()),
        "target_word_count": len(words),
        "matched_word_count": len(results),
        "models": model_summary,
        "hit_words_by_label": {
            style: {
                label: label_hit_words[(style, label)]
                for label in sorted(models.get(style, {}))
            }
            for style in sorted(models)
        },
        "perfect_bbox_hit_words_by_label": {
            style: {
                label: exact_hit_words[(style, label)]
                for label in sorted(models.get(style, {}))
            }
            for style in sorted(models)
        },
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
