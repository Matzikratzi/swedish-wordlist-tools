from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .ocr_manual_pixel_atlas_match import _ink_pixels, _load_templates, _template_models
from .ocr_expected_word_decode_v2 import (
    _beam_decode,
    _candidate_hits,
    _select_words,
    _split_residual,
)


def _label_occurs(expected: str, label: str) -> bool:
    if not label:
        return False
    return any(expected.startswith(label, i) for i in range(len(expected)))


def _active_rel_zone(
    *,
    expected: str,
    style_models: dict[str, list[dict[str, object]]],
    pad_above: int,
    pad_below: int,
) -> tuple[int, int, str]:
    """Return plausible y range relative to baseline for this expected word.

    The range is learned from all atlas models whose labels can occur in the
    expected string.  This keeps the source crop generous while preventing ink
    from neighbouring text rows from counting as residual for the word.
    """
    tops: list[int] = []
    bottoms: list[int] = []
    for label, models in style_models.items():
        if not _label_occurs(expected, label):
            continue
        for model in models:
            height = int(model.get("height") or 0)
            baseline_offset = int(model.get("baseline_offset") or 0)
            if height <= 0:
                continue
            tops.append(-baseline_offset)
            bottoms.append(height - 1 - baseline_offset)

    if tops:
        return min(tops) - pad_above, max(bottoms) + pad_below, "atlas-model-union"

    # Only relevant before a style has useful facit. Keep this conservative;
    # missing-glyph cases are exceptions anyway, so residual filtering must not
    # hide evidence merely because the atlas is empty for that style.
    has_capital = any(ch.isalpha() and ch.upper() == ch and ch.lower() != ch for ch in expected)
    has_high_mark = any(ch in "ijåäöÅÄÖéÉüÜ" for ch in expected)
    top = -14 if has_capital else (-11 if has_high_mark else -10)
    return top - pad_above, 4 + pad_below, "fallback-typographic"


def _trial(
    *,
    expected: str,
    style: str,
    style_models: dict[str, list[dict[str, object]]],
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    max_missing: int,
    max_extra: int,
    beam_width: int,
    missing_penalty: float,
    active_pad_above: int,
    active_pad_below: int,
) -> dict[str, object]:
    rel_top, rel_bottom, zone_method = _active_rel_zone(
        expected=expected,
        style_models=style_models,
        pad_above=active_pad_above,
        pad_below=active_pad_below,
    )

    best: dict[str, object] | None = None
    for baseline in range(height):
        by_pos = _candidate_hits(
            expected=expected,
            style_models=style_models,
            ink=ink,
            width=width,
            height=height,
            baseline=baseline,
            max_missing=max_missing,
            max_extra=max_extra,
        )
        beam = _beam_decode(
            expected=expected,
            by_pos=by_pos,
            beam_width=beam_width,
            missing_penalty=missing_penalty,
        )
        used = set(beam.used)

        y0 = max(0, baseline + rel_top)
        y1 = min(height - 1, baseline + rel_bottom)
        active_ink = {(x, y) for x, y in ink if y0 <= y <= y1}

        if beam.picks:
            xmin = min(int(h["x"]) for h in beam.picks)
            xmax = max(int(h["x"]) + int(h["width"]) - 1 for h in beam.picks)
            core_ink = {(x, y) for x, y in active_ink if xmin <= x <= xmax}
            ignored_outside = {
                (x, y) for x, y in ink
                if xmin <= x <= xmax and not (y0 <= y <= y1)
            }
        else:
            core_ink = active_ink
            ignored_outside = ink - active_ink

        unexplained = core_ink - used
        attached, orphan = _split_residual(unexplained, used)
        complete = beam.pos == len(expected) and not beam.missing
        score_key = (
            1 if complete else 0,
            -len(beam.missing),
            len(used),
            -len(orphan),
            -len(attached),
            beam.score,
        )
        item = {
            "style": style,
            "baseline_y": baseline,
            "complete": complete,
            "missing_labels": list(beam.missing),
            "explained_pixels": len(used),
            "unexplained_pixels": len(unexplained),
            "attached_residual_pixels": len(attached),
            "orphan_residual_pixels": len(orphan),
            "ignored_outside_active_zone_pixels": len(ignored_outside),
            "active_y_min": y0,
            "active_y_max": y1,
            "active_rel_top": rel_top,
            "active_rel_bottom": rel_bottom,
            "active_zone_method": zone_method,
            "score": round(beam.score, 4),
            "score_key": score_key,
            "picks": [dict(h) for h in beam.picks],
        }
        if best is None or tuple(item["score_key"]) > tuple(best["score_key"]):
            best = item
    assert best is not None
    return best


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Expected-word decoder v3: generous image crops, atlas-derived active vertical residual zone."
    )
    ap.add_argument("atlas", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--max-same-word", type=int, default=3)
    ap.add_argument("--max-pl", type=int, default=0)
    ap.add_argument("--ink-threshold", type=int, default=210)
    ap.add_argument("--max-missing", type=int, default=0)
    ap.add_argument("--max-extra", type=int, default=4)
    ap.add_argument("--beam-width", type=int, default=160)
    ap.add_argument("--missing-penalty", type=float, default=120.0)
    ap.add_argument("--max-orphan", type=int, default=0)
    ap.add_argument("--attached-budget-per-pick", type=int, default=-1)
    ap.add_argument("--active-pad-above", type=int, default=1)
    ap.add_argument("--active-pad-below", type=int, default=1)
    ap.add_argument("--split-gap", type=int, default=5)
    ap.add_argument("--include-reference-words", action="store_true")
    ap.add_argument("--include-resolved", action="store_true")
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
    words = _select_words(words, limit=args.limit, max_same_word=args.max_same_word, max_pl=args.max_pl)

    attached_budget_per_pick = args.max_extra if args.attached_budget_per_pick < 0 else args.attached_budget_per_pick
    stats = Counter()
    results: list[dict[str, object]] = []

    for word in words:
        expected = str(word.get("expected_word") or "")
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not expected or not rel or not path.exists():
            stats["skipped-invalid"] += 1
            continue

        ink, width, height = _ink_pixels(path, args.ink_threshold)
        trials = []
        for style, style_models in models.items():
            if not style_models:
                continue
            trials.append(_trial(
                expected=expected,
                style=style,
                style_models=style_models,
                ink=ink,
                width=width,
                height=height,
                max_missing=args.max_missing,
                max_extra=args.max_extra,
                beam_width=args.beam_width,
                missing_penalty=args.missing_penalty,
                active_pad_above=args.active_pad_above,
                active_pad_below=args.active_pad_below,
            ))
        if not trials:
            stats["no-style-models"] += 1
            continue

        manifest_style = str(word.get("style") or "")
        best = max(trials, key=lambda t: (tuple(t["score_key"]), 1 if t["style"] == manifest_style else 0))
        attached_budget = attached_budget_per_pick * len(best["picks"])
        resolved = (
            bool(best["complete"])
            and int(best["orphan_residual_pixels"]) <= args.max_orphan
            and int(best["attached_residual_pixels"]) <= attached_budget
        )

        if resolved:
            stats["resolved"] += 1
        else:
            stats["exceptions"] += 1
            if best["missing_labels"]:
                stats["missing-glyph-or-cluster"] += 1
            if int(best["orphan_residual_pixels"]) > args.max_orphan:
                stats["orphan-residual"] += 1
            if int(best["attached_residual_pixels"]) > attached_budget:
                stats["attached-residual-over-budget"] += 1

        matches: dict[str, list[dict[str, object]]] = defaultdict(list)
        for h0 in best["picks"]:
            h = dict(h0)
            label = str(h.pop("label"))
            h.pop("char_start", None)
            h.pop("char_end", None)
            matches[label].append(h)

        if (not resolved) or args.include_resolved:
            row = dict(word)
            row.update({
                "style": str(best["style"]),
                "manifest_style": manifest_style,
                "style_changed": bool(manifest_style and best["style"] != manifest_style),
                "width": width,
                "height": height,
                "baseline_y": int(best["baseline_y"]),
                "baseline_method": "expected-word-global-v3-active-zone",
                "matches": dict(matches),
                "rejected_candidates": {},
                "decode_resolved": resolved,
                "decode_missing_labels": best["missing_labels"],
                "decode_explained_pixels": best["explained_pixels"],
                "decode_unexplained_pixels": best["unexplained_pixels"],
                "decode_attached_residual_pixels": best["attached_residual_pixels"],
                "decode_orphan_residual_pixels": best["orphan_residual_pixels"],
                "decode_attached_budget": attached_budget,
                "decode_ignored_outside_active_zone_pixels": best["ignored_outside_active_zone_pixels"],
                "decode_active_y_min": best["active_y_min"],
                "decode_active_y_max": best["active_y_max"],
                "decode_active_rel_top": best["active_rel_top"],
                "decode_active_rel_bottom": best["active_rel_bottom"],
                "decode_active_zone_method": best["active_zone_method"],
                "decode_trials": {
                    str(t["style"]): {
                        "complete": t["complete"],
                        "missing_labels": t["missing_labels"],
                        "explained_pixels": t["explained_pixels"],
                        "attached_residual_pixels": t["attached_residual_pixels"],
                        "orphan_residual_pixels": t["orphan_residual_pixels"],
                        "ignored_outside_active_zone_pixels": t["ignored_outside_active_zone_pixels"],
                        "active_y_min": t["active_y_min"],
                        "active_y_max": t["active_y_max"],
                        "baseline_y": t["baseline_y"],
                        "score": t["score"],
                    }
                    for t in trials
                },
            })
            results.append(row)

    payload = {
        "format": "saol-expected-word-decode-v1",
        "decoder_version": 3,
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": sum(len(ms) for labels in models.values() for ms in labels.values()),
        "target_word_count": len(words),
        "exception_word_count": int(stats["exceptions"]),
        "resolved_word_count": int(stats["resolved"]),
        "stats": dict(sorted(stats.items())),
        "settings": {
            "ink_threshold": args.ink_threshold,
            "max_missing": args.max_missing,
            "max_extra": args.max_extra,
            "beam_width": args.beam_width,
            "missing_penalty": args.missing_penalty,
            "max_orphan": args.max_orphan,
            "attached_budget_per_pick": attached_budget_per_pick,
            "active_pad_above": args.active_pad_above,
            "active_pad_below": args.active_pad_below,
            "max_same_word": args.max_same_word,
            "max_pl": args.max_pl,
        },
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
