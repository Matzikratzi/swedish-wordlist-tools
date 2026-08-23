from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .ocr_manual_pixel_atlas_match import (
    _guess_baseline,
    _ink_pixels,
    _load_templates,
    _nonoverlap,
    _scan_model,
    _template_models,
)
from .ocr_manual_pixel_atlas_match_v2 import _augment_hit

# User-verified ordinary letters that stand on the support line.  Descenders are
# deliberately omitted; they can still be matched after the baseline is known.
BASELINE_ANCHORS = set("abcdehiklmnorstuvwxåäö")
# These tiny marks are dangerous if allowed to float vertically inside unknown
# glyphs.  Once a baseline is chosen they must occur at their learned y-position.
STRICT_Y_LABELS = {".", "·", "-", ","}


def _global_nonoverlap(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """Choose largest exact candidates first; a raster pixel may be used once."""
    chosen: list[dict[str, object]] = []
    used: set[tuple[int, int]] = set()
    for hit in sorted(
        candidates,
        key=lambda h: (
            -len(h.get("matched_pixels", [])),
            float(h.get("score", 0.0)),
            -int(h.get("template_source_count", 0)),
            int(h.get("x", 0)),
        ),
    ):
        pts = {tuple(p) for p in hit.get("matched_pixels", [])}
        if pts & used:
            continue
        chosen.append(hit)
        used |= pts
    return chosen


def _vote_baseline(
    *,
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    style_models: dict[str, list[dict[str, object]]],
    geometric_baseline: int,
    max_missing: int,
    max_extra: int,
) -> tuple[int, int, dict[int, int]]:
    """Let exact ordinary glyphs vote for the support-line y coordinate."""
    scores: dict[int, tuple[int, int, int]] = {}
    vote_counts: dict[int, int] = {}
    for baseline in range(height):
        candidates: list[dict[str, object]] = []
        for label in BASELINE_ANCHORS:
            for model_index, model in enumerate(style_models.get(label, [])):
                for raw in _scan_model(
                    ink=ink,
                    width=width,
                    height=height,
                    baseline=baseline,
                    model=model,
                    baseline_tolerance=0,
                    max_missing=max_missing,
                    max_extra=max_extra,
                ):
                    if int(raw["missing"]) != 0:
                        continue
                    hit = _augment_hit(raw, model, ink)
                    hit["label"] = label
                    hit["model_index"] = model_index
                    candidates.append(hit)
        winners = _global_nonoverlap(candidates)
        # Primary score: number of agreeing glyphs. Secondary: explained pixels.
        # Tertiary: stay close to the old geometric guess when tied.
        votes = len(winners)
        pixels = sum(len(h.get("matched_pixels", [])) for h in winners)
        scores[baseline] = (votes, pixels, -abs(baseline - geometric_baseline))
        vote_counts[baseline] = votes
    best = max(scores, key=scores.get) if scores else geometric_baseline
    votes = scores.get(best, (0, 0, 0))[0]
    if votes == 0:
        return geometric_baseline, 0, vote_counts
    return best, votes, vote_counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pixel matcher with glyph-voted baseline and strict vertical placement for tiny marks."
    )
    ap.add_argument("atlas", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--ink-threshold", type=int, default=210)
    ap.add_argument("--baseline-tolerance", type=int, default=1)
    ap.add_argument("--max-missing", type=int, default=0)
    ap.add_argument("--max-extra", type=int, default=4)
    ap.add_argument("--split-gap", type=int, default=5)
    ap.add_argument("--hits-per-label", type=int, default=6)
    ap.add_argument("--include-reference-words", action="store_true")
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
    hit_words: Counter[tuple[str, str]] = Counter()

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
        geometric_baseline, geometric_confidence = _guess_baseline(path, args.ink_threshold)
        baseline, baseline_votes, vote_map = _vote_baseline(
            ink=ink,
            width=width,
            height=height,
            style_models=style_models,
            geometric_baseline=geometric_baseline,
            max_missing=args.max_missing,
            max_extra=args.max_extra,
        )

        matches: dict[str, list[dict[str, object]]] = {}
        all_candidates: list[dict[str, object]] = []
        for label, label_models in style_models.items():
            label_hits: list[dict[str, object]] = []
            tolerance = 0 if label in STRICT_Y_LABELS else args.baseline_tolerance
            for model_index, model in enumerate(label_models):
                for raw in _scan_model(
                    ink=ink,
                    width=width,
                    height=height,
                    baseline=baseline,
                    model=model,
                    baseline_tolerance=tolerance,
                    max_missing=args.max_missing,
                    max_extra=args.max_extra,
                ):
                    hit = _augment_hit(raw, model, ink)
                    hit["model_index"] = model_index
                    hit["label"] = label
                    hit["candidate_status"] = (
                        "connected" if int(hit.get("external_contacts", 0)) else "accepted"
                    )
                    label_hits.append(hit)
            label_hits.sort(
                key=lambda h: (
                    float(h["score"]),
                    -int(h["template_source_count"]),
                    abs(int(h["baseline_dy"])),
                    int(h["x"]),
                )
            )
            for h in _nonoverlap(label_hits, args.hits_per_label):
                all_candidates.append(h)

        # One pixel, one automatic interpretation: largest candidate wins.
        winners = _global_nonoverlap(all_candidates)
        for hit in winners:
            label = str(hit.pop("label"))
            matches.setdefault(label, []).append(hit)
            hit_words[(style, label)] += 1

        if matches:
            results.append(
                {
                    "source_id": str(word.get("source_id") or ""),
                    "subnr": str(word.get("subnr") or ""),
                    "page": word.get("page"),
                    "column": word.get("column"),
                    "column_left": word.get("column_left"),
                    "word_bbox": word.get("word_bbox"),
                    "style": style,
                    "expected_word": str(word.get("expected_word") or ""),
                    "headword": str(word.get("headword") or ""),
                    "word_file": rel,
                    "width": width,
                    "height": height,
                    "baseline_y": baseline,
                    "baseline_method": "glyph-vote" if baseline_votes else "geometry-fallback",
                    "baseline_votes": baseline_votes,
                    "geometric_baseline_y": geometric_baseline,
                    "geometric_baseline_confidence": round(geometric_confidence, 4),
                    "baseline_vote_map": vote_map,
                    "matches": matches,
                    "rejected_candidates": {},
                }
            )

    nested: dict[str, dict[str, int]] = {}
    for (style, label), n in sorted(hit_words.items()):
        nested.setdefault(style, {})[label] = n

    payload = {
        "format": "saol-manual-pixel-transfer-v4",
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": sum(len(ms) for labels in models.values() for ms in labels.values()),
        "target_word_count": len(words),
        "candidate_word_count": len(results),
        "hit_words_by_label": nested,
        "settings": {
            "ink_threshold": args.ink_threshold,
            "baseline_tolerance": args.baseline_tolerance,
            "strict_y_labels": sorted(STRICT_Y_LABELS),
            "baseline_anchor_labels": sorted(BASELINE_ANCHORS),
            "max_missing": args.max_missing,
            "max_extra": args.max_extra,
        },
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
