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


def _external_contacts(
    ink: set[tuple[int, int]], transformed: set[tuple[int, int]]
) -> set[tuple[int, int]]:
    """Ink outside a proposed glyph touching it in the 8-neighbourhood."""
    contacts: set[tuple[int, int]] = set()
    for x, y in transformed:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                q = (x + dx, y + dy)
                if q in ink and q not in transformed:
                    contacts.add(q)
    return contacts


def _augment_hit(
    hit: dict[str, object], model: dict[str, object], ink: set[tuple[int, int]]
) -> dict[str, object]:
    x0, y0 = int(hit["x"]), int(hit["y"])
    pixels = model["pixels"]
    assert isinstance(pixels, tuple)
    transformed = {(x0 + int(x), y0 + int(y)) for x, y in pixels}
    contacts = _external_contacts(ink, transformed)
    out = dict(hit)
    out["matched_pixels"] = [list(p) for p in sorted(transformed, key=lambda p: (p[1], p[0]))]
    out["external_contact_pixels"] = [list(p) for p in sorted(contacts, key=lambda p: (p[1], p[0]))]
    out["external_contacts"] = len(contacts)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Baseline-aware manual pixel matcher with strict external-topology filtering."
    )
    ap.add_argument("atlas", type=Path, help="Manual pixel atlas JSON (v1/v3/v4 compatible)")
    ap.add_argument("library", type=Path, help="Mixed-style word-segment library")
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--ink-threshold", type=int, default=210)
    ap.add_argument("--baseline-tolerance", type=int, default=1)
    ap.add_argument("--max-missing", type=int, default=0)
    ap.add_argument("--max-extra", type=int, default=4)
    ap.add_argument("--max-external-contacts", type=int, default=0)
    ap.add_argument("--split-gap", type=int, default=5)
    ap.add_argument("--hits-per-label", type=int, default=4)
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
    perfect_words: Counter[tuple[str, str]] = Counter()
    rejected_topology: Counter[tuple[str, str]] = Counter()

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
            candidates: list[dict[str, object]] = []
            for model_index, model in enumerate(label_models):
                raw_hits = _scan_model(
                    ink=ink,
                    width=width,
                    height=height,
                    baseline=baseline,
                    model=model,
                    baseline_tolerance=args.baseline_tolerance,
                    max_missing=args.max_missing,
                    max_extra=args.max_extra,
                )
                for raw in raw_hits:
                    hit = _augment_hit(raw, model, ink)
                    hit["model_index"] = model_index
                    if int(hit["external_contacts"]) > args.max_external_contacts:
                        rejected_topology[(style, label)] += 1
                        continue
                    candidates.append(hit)
            candidates.sort(
                key=lambda h: (
                    int(h["external_contacts"]),
                    float(h["score"]),
                    -int(h["template_source_count"]),
                    abs(int(h["baseline_dy"])),
                    int(h["x"]),
                )
            )
            chosen = _nonoverlap(candidates, args.hits_per_label)
            if chosen:
                matches[label] = chosen
                hit_words[(style, label)] += 1
                if any(
                    int(h["missing"]) == 0
                    and int(h["extra"]) == 0
                    and int(h["external_contacts"]) == 0
                    for h in chosen
                ):
                    perfect_words[(style, label)] += 1

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

    def nested(counter: Counter[tuple[str, str]]) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for (style, label), n in sorted(counter.items()):
            out.setdefault(style, {})[label] = n
        return out

    model_count = sum(len(ms) for labels in models.values() for ms in labels.values())
    payload = {
        "format": "saol-manual-pixel-transfer-v2",
        "atlas": str(args.atlas),
        "library": str(args.library),
        "reference_template_count": len(templates),
        "model_count": model_count,
        "target_word_count": len(words),
        "matched_word_count": len(results),
        "hit_words_by_label": nested(hit_words),
        "perfect_topological_hit_words_by_label": nested(perfect_words),
        "rejected_candidates_by_topology": nested(rejected_topology),
        "settings": {
            "ink_threshold": args.ink_threshold,
            "baseline_tolerance": args.baseline_tolerance,
            "max_missing": args.max_missing,
            "max_extra": args.max_extra,
            "max_external_contacts": args.max_external_contacts,
        },
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
