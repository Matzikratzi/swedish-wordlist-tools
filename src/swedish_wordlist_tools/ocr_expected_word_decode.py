from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .ocr_manual_pixel_atlas_match import _ink_pixels, _load_templates, _scan_model, _template_models
from .ocr_manual_pixel_atlas_match_v2 import _augment_hit
from .ocr_manual_pixel_atlas_match_v4 import BASELINE_ANCHORS, STRICT_Y_LABELS, _anchor_model


@dataclass
class Beam:
    pos: int
    score: float
    used: frozenset[tuple[int, int]]
    last_x: int
    picks: tuple[dict[str, object], ...]
    missing: tuple[str, ...]


def _candidate_hits(*, expected: str, style_models: dict[str, list[dict[str, object]]], ink: set[tuple[int, int]], width: int, height: int, baseline: int, max_missing: int, max_extra: int) -> dict[int, list[dict[str, object]]]:
    by_pos: dict[int, list[dict[str, object]]] = defaultdict(list)
    for i in range(len(expected)):
        for label, models in style_models.items():
            if not label or not expected.startswith(label, i):
                continue
            for model_index, original_model in enumerate(models):
                model = _anchor_model(original_model) if label in BASELINE_ANCHORS else original_model
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
                    hit = _augment_hit(raw, model, ink)
                    pts = frozenset(tuple(p) for p in hit.get("matched_pixels", []))
                    if not pts:
                        continue
                    hit = dict(hit)
                    hit["label"] = label
                    hit["model_index"] = model_index
                    hit["char_start"] = i
                    hit["char_end"] = i + len(label)
                    hit["matched_pixels"] = [list(p) for p in sorted(pts)]
                    hit["candidate_status"] = "connected" if int(hit.get("external_contacts", 0)) else "accepted"
                    by_pos[i].append(hit)
        by_pos[i].sort(key=lambda h: (-len(h.get("matched_pixels", [])), float(h.get("score", 0.0)), -int(h.get("template_source_count", 0)), int(h.get("x", 0))))
    return by_pos


def _beam_decode(*, expected: str, by_pos: dict[int, list[dict[str, object]]], beam_width: int, missing_penalty: float) -> Beam:
    beams = [Beam(0, 0.0, frozenset(), -10_000, (), ())]
    while beams:
        if all(b.pos >= len(expected) for b in beams):
            break
        nxt: list[Beam] = []
        for b in beams:
            if b.pos >= len(expected):
                nxt.append(b)
                continue
            # Missing-character fallback keeps the decoder moving and makes the
            # exact position of an unknown glyph visible in the exception output.
            nxt.append(Beam(b.pos + 1, b.score - missing_penalty, b.used, b.last_x, b.picks, b.missing + (expected[b.pos],)))
            for h in by_pos.get(b.pos, []):
                pts = frozenset(tuple(p) for p in h.get("matched_pixels", []))
                if pts & b.used:
                    continue
                x0 = int(h.get("x", 0))
                # Reading order is by left edge, but overlapping x-ranges are
                # allowed for slanted/connected typography.
                if x0 + 2 < b.last_x:
                    continue
                gain = 10.0 * len(pts) + 1.5 * int(h.get("template_source_count", 0)) - 2.0 * int(h.get("extra", 0)) - float(h.get("score", 0.0))
                nxt.append(Beam(int(h["char_end"]), b.score + gain, b.used | pts, x0, b.picks + (h,), b.missing))
        # Deduplicate coarse-equivalent states, then retain the strongest beam.
        best: dict[tuple[int, int, int], Beam] = {}
        for b in nxt:
            key = (b.pos, b.last_x, len(b.used))
            old = best.get(key)
            if old is None or b.score > old.score:
                best[key] = b
        beams = sorted(best.values(), key=lambda b: (b.pos == len(expected), b.score, len(b.used)), reverse=True)[:beam_width]
    return max(beams, key=lambda b: (b.pos == len(expected), -len(b.missing), b.score, len(b.used)))


def _trial(*, expected: str, style: str, style_models: dict[str, list[dict[str, object]]], ink: set[tuple[int, int]], width: int, height: int, max_missing: int, max_extra: int, beam_width: int, missing_penalty: float) -> dict[str, object]:
    best: dict[str, object] | None = None
    for baseline in range(height):
        by_pos = _candidate_hits(expected=expected, style_models=style_models, ink=ink, width=width, height=height, baseline=baseline, max_missing=max_missing, max_extra=max_extra)
        beam = _beam_decode(expected=expected, by_pos=by_pos, beam_width=beam_width, missing_penalty=missing_penalty)
        used = set(beam.used)
        if beam.picks:
            xmin = min(int(h["x"]) for h in beam.picks)
            xmax = max(int(h["x"]) + int(h["width"]) - 1 for h in beam.picks)
            core_ink = {(x, y) for x, y in ink if xmin <= x <= xmax}
        else:
            core_ink = set(ink)
        unexplained = core_ink - used
        complete = beam.pos == len(expected) and not beam.missing
        score_key = (1 if complete else 0, -len(beam.missing), len(used), -len(unexplained), beam.score)
        item = {
            "style": style,
            "baseline_y": baseline,
            "complete": complete,
            "missing_labels": list(beam.missing),
            "explained_pixels": len(used),
            "unexplained_pixels": len(unexplained),
            "score": round(beam.score, 4),
            "score_key": score_key,
            "picks": [dict(h) for h in beam.picks],
        }
        if best is None or tuple(item["score_key"]) > tuple(best["score_key"]):
            best = item
    assert best is not None
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Decode known expected word strings from manual pixel glyph/cluster templates and emit only exceptions by default.")
    ap.add_argument("atlas", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--limit", type=int, default=500, help="Maximum unseen target words to test (0 = all)")
    ap.add_argument("--ink-threshold", type=int, default=210)
    ap.add_argument("--max-missing", type=int, default=0)
    ap.add_argument("--max-extra", type=int, default=4)
    ap.add_argument("--beam-width", type=int, default=160)
    ap.add_argument("--missing-penalty", type=float, default=120.0)
    ap.add_argument("--max-unexplained", type=int, default=2, help="Resolved words may leave at most this many core ink pixels unexplained")
    ap.add_argument("--split-gap", type=int, default=5)
    ap.add_argument("--include-reference-words", action="store_true")
    ap.add_argument("--include-resolved", action="store_true", help="Also include fully resolved words in results")
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
    if args.limit > 0:
        words = words[:args.limit]

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
            trials.append(_trial(expected=expected, style=style, style_models=style_models, ink=ink, width=width, height=height, max_missing=args.max_missing, max_extra=args.max_extra, beam_width=args.beam_width, missing_penalty=args.missing_penalty))
        if not trials:
            stats["no-style-models"] += 1
            continue
        manifest_style = str(word.get("style") or "")
        best = max(trials, key=lambda t: (tuple(t["score_key"]), 1 if t["style"] == manifest_style else 0))
        resolved = bool(best["complete"]) and int(best["unexplained_pixels"]) <= args.max_unexplained
        if resolved:
            stats["resolved"] += 1
        else:
            stats["exceptions"] += 1
            if best["missing_labels"]:
                stats["missing-glyph-or-cluster"] += 1
            if int(best["unexplained_pixels"]) > args.max_unexplained:
                stats["unexplained-ink"] += 1

        matches: dict[str, list[dict[str, object]]] = defaultdict(list)
        for h0 in best["picks"]:
            h = dict(h0)
            label = str(h.pop("label"))
            h.pop("char_start", None)
            h.pop("char_end", None)
            matches[label].append(h)

        if (not resolved) or args.include_resolved:
            results.append({
                "source_id": str(word.get("source_id") or ""),
                "subnr": str(word.get("subnr") or ""),
                "page": word.get("page"),
                "column": word.get("column"),
                "column_left": word.get("column_left"),
                "word_bbox": word.get("word_bbox"),
                "style": str(best["style"]),
                "manifest_style": manifest_style,
                "style_changed": bool(manifest_style and best["style"] != manifest_style),
                "expected_word": expected,
                "headword": str(word.get("headword") or ""),
                "word_file": rel,
                "width": width,
                "height": height,
                "baseline_y": int(best["baseline_y"]),
                "baseline_method": "expected-word-global",
                "matches": dict(matches),
                "rejected_candidates": {},
                "decode_resolved": resolved,
                "decode_missing_labels": best["missing_labels"],
                "decode_explained_pixels": best["explained_pixels"],
                "decode_unexplained_pixels": best["unexplained_pixels"],
                "decode_trials": {str(t["style"]): {"complete": t["complete"], "missing_labels": t["missing_labels"], "explained_pixels": t["explained_pixels"], "unexplained_pixels": t["unexplained_pixels"], "baseline_y": t["baseline_y"], "score": t["score"]} for t in trials},
            })

    payload = {
        "format": "saol-expected-word-decode-v1",
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": sum(len(ms) for labels in models.values() for ms in labels.values()),
        "target_word_count": len(words),
        "exception_word_count": int(stats["exceptions"]),
        "resolved_word_count": int(stats["resolved"]),
        "stats": dict(sorted(stats.items())),
        "settings": {"ink_threshold": args.ink_threshold, "max_missing": args.max_missing, "max_extra": args.max_extra, "beam_width": args.beam_width, "missing_penalty": args.missing_penalty, "max_unexplained": args.max_unexplained},
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
