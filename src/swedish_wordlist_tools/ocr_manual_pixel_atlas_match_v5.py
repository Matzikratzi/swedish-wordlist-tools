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
from .ocr_manual_pixel_atlas_match_v4 import (
    BASELINE_ANCHORS,
    STRICT_Y_LABELS,
    _anchor_model,
    _global_nonoverlap,
    _vote_baseline,
)


def _style_result(
    *,
    style: str,
    style_models: dict[str, list[dict[str, object]]],
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    geometric_baseline: int,
    geometric_confidence: float,
    baseline_tolerance: int,
    max_missing: int,
    max_extra: int,
    hits_per_label: int,
) -> dict[str, object]:
    baseline, baseline_votes, vote_map = _vote_baseline(
        ink=ink,
        width=width,
        height=height,
        style_models=style_models,
        geometric_baseline=geometric_baseline,
        max_missing=max_missing,
        max_extra=max_extra,
    )

    all_candidates: list[dict[str, object]] = []
    for label, label_models in style_models.items():
        label_hits: list[dict[str, object]] = []
        tolerance = 0 if label in STRICT_Y_LABELS else baseline_tolerance
        for model_index, original_model in enumerate(label_models):
            model = _anchor_model(original_model) if label in BASELINE_ANCHORS else original_model
            for raw in _scan_model(
                ink=ink,
                width=width,
                height=height,
                baseline=baseline,
                model=model,
                baseline_tolerance=tolerance,
                max_missing=max_missing,
                max_extra=max_extra,
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
        all_candidates.extend(_nonoverlap(label_hits, hits_per_label))

    winners = _global_nonoverlap(all_candidates)
    matches: dict[str, list[dict[str, object]]] = {}
    explained: set[tuple[int, int]] = set()
    total_score = 0.0
    source_support = 0
    for original in winners:
        hit = dict(original)
        label = str(hit.pop("label"))
        matches.setdefault(label, []).append(hit)
        explained |= {tuple(p) for p in hit.get("matched_pixels", [])}
        total_score += float(hit.get("score", 0.0))
        source_support += int(hit.get("template_source_count", 0))

    # Style choice is dominated by how much distinct ink it explains.  Number of
    # non-overlapping glyphs and independent template support break close cases;
    # low residual score is only a later tie-breaker.
    style_score = (
        len(explained),
        len(winners),
        source_support,
        -total_score,
        baseline_votes,
    )
    return {
        "style": style,
        "matches": matches,
        "winners": winners,
        "explained_pixels": len(explained),
        "winner_count": len(winners),
        "source_support": source_support,
        "total_score": round(total_score, 4),
        "style_score": style_score,
        "baseline_y": baseline,
        "baseline_method": "glyph-vote" if baseline_votes else "geometry-fallback",
        "baseline_votes": baseline_votes,
        "baseline_vote_map": vote_map,
        "geometric_baseline_y": geometric_baseline,
        "geometric_baseline_confidence": round(geometric_confidence, 4),
    }


def _diverse_words(
    words: list[dict[str, object]], *, limit: int, max_same_word: int, max_pl: int
) -> list[dict[str, object]]:
    counts: Counter[str] = Counter()
    out: list[dict[str, object]] = []
    for word in words:
        expected = str(word.get("expected_word") or "")
        cap = max_pl if expected == "pl." else max_same_word
        if cap > 0 and counts[expected] >= cap:
            continue
        counts[expected] += 1
        out.append(word)
        if limit > 0 and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Baseline-aware pixel matcher that lets roman/italic/bold compete per word."
    )
    ap.add_argument("atlas", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument(
        "--style",
        choices=("roman", "italic", "bold"),
        help="Force one style; default tries every style represented in the atlas",
    )
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-same-word", type=int, default=3)
    ap.add_argument("--max-pl", type=int, default=2)
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
    if not args.include_reference_words:
        words = [w for w in words if str(w.get("source_id") or "") not in reference_source_ids]
    words = _diverse_words(
        words,
        limit=args.limit,
        max_same_word=args.max_same_word,
        max_pl=args.max_pl,
    )

    results: list[dict[str, object]] = []
    hit_words: Counter[tuple[str, str]] = Counter()
    chosen_styles: Counter[str] = Counter()
    style_corrections = 0

    for word in words:
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not rel or not path.exists():
            continue
        ink, width, height = _ink_pixels(path, args.ink_threshold)
        geometric_baseline, geometric_confidence = _guess_baseline(path, args.ink_threshold)
        manifest_style = str(word.get("style") or "")

        styles = [args.style] if args.style else sorted(models)
        trials: list[dict[str, object]] = []
        for style in styles:
            style_models = models.get(style or "", {})
            if not style_models:
                continue
            trial = _style_result(
                style=str(style),
                style_models=style_models,
                ink=ink,
                width=width,
                height=height,
                geometric_baseline=geometric_baseline,
                geometric_confidence=geometric_confidence,
                baseline_tolerance=args.baseline_tolerance,
                max_missing=args.max_missing,
                max_extra=args.max_extra,
                hits_per_label=args.hits_per_label,
            )
            trials.append(trial)

        if not trials:
            continue

        # Manifest typography is only the final tie-breaker, never a filter.
        best = max(
            trials,
            key=lambda t: (
                tuple(t["style_score"]),
                1 if str(t["style"]) == manifest_style else 0,
            ),
        )
        matches = best["matches"]
        if not matches:
            continue
        chosen_style = str(best["style"])
        chosen_styles[chosen_style] += 1
        if manifest_style and chosen_style != manifest_style:
            style_corrections += 1
        for label, hits in matches.items():
            if hits:
                hit_words[(chosen_style, str(label))] += 1

        style_trials = {
            str(t["style"]): {
                "explained_pixels": t["explained_pixels"],
                "winner_count": t["winner_count"],
                "source_support": t["source_support"],
                "total_score": t["total_score"],
                "baseline_y": t["baseline_y"],
                "baseline_votes": t["baseline_votes"],
            }
            for t in trials
        }

        results.append(
            {
                "source_id": str(word.get("source_id") or ""),
                "subnr": str(word.get("subnr") or ""),
                "page": word.get("page"),
                "column": word.get("column"),
                "column_left": word.get("column_left"),
                "word_bbox": word.get("word_bbox"),
                "style": chosen_style,
                "manifest_style": manifest_style,
                "style_changed": bool(manifest_style and chosen_style != manifest_style),
                "style_trials": style_trials,
                "expected_word": str(word.get("expected_word") or ""),
                "headword": str(word.get("headword") or ""),
                "word_file": rel,
                "width": width,
                "height": height,
                "baseline_y": best["baseline_y"],
                "baseline_method": best["baseline_method"],
                "baseline_votes": best["baseline_votes"],
                "geometric_baseline_y": best["geometric_baseline_y"],
                "geometric_baseline_confidence": best["geometric_baseline_confidence"],
                "baseline_vote_map": best["baseline_vote_map"],
                "matches": matches,
                "rejected_candidates": {},
            }
        )

    nested: dict[str, dict[str, int]] = {}
    for (style, label), n in sorted(hit_words.items()):
        nested.setdefault(style, {})[label] = n

    payload = {
        "format": "saol-manual-pixel-transfer-v5",
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": sum(len(ms) for labels in models.values() for ms in labels.values()),
        "target_word_count": len(words),
        "candidate_word_count": len(results),
        "chosen_styles": dict(sorted(chosen_styles.items())),
        "style_corrections_from_manifest": style_corrections,
        "hit_words_by_label": nested,
        "settings": {
            "ink_threshold": args.ink_threshold,
            "baseline_tolerance": args.baseline_tolerance,
            "strict_y_labels": sorted(STRICT_Y_LABELS),
            "baseline_anchor_labels": sorted(BASELINE_ANCHORS),
            "max_missing": args.max_missing,
            "max_extra": args.max_extra,
            "max_same_word": args.max_same_word,
            "max_pl": args.max_pl,
            "style_competition": args.style is None,
        },
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
