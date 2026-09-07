from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import build_consensus, classify_consensus_models


def _safe_label(text: str) -> str:
    return "".join(ch if ch.isalnum() else f"u{ord(ch):04x}" for ch in text)


def _materialize(
    library: Path,
    words: list[dict[str, object]],
    *,
    style: str,
    excluded_source: int,
    excluded_subnr: object,
    root: Path,
    kind: str,
    min_sources: int = 1,
) -> tuple[list[Path], dict[str, int]]:
    grouped: dict[str, list[tuple[int, object, Path]]] = defaultdict(list)
    for word in words:
        if word.get("style") != style:
            continue
        source_id = int(word.get("source_id", -1))
        subnr = word.get("subnr")
        if source_id == excluded_source or subnr == excluded_subnr:
            continue
        if kind == "glyph":
            items = word.get("glyphs", [])
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                label, rel = item.get("character"), item.get("file")
                if isinstance(label, str) and isinstance(rel, str):
                    grouped[label].append((source_id, subnr, library / rel))
        else:
            items = word.get("segments", [])
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict) or item.get("kind") != "cluster":
                    continue
                label, rel = item.get("expected_text"), item.get("file")
                if isinstance(label, str) and isinstance(rel, str):
                    grouped[label].append((source_id, subnr, library / rel))

    eligible = {
        label: refs for label, refs in grouped.items()
        if len({(sid, sub) for sid, sub, _p in refs}) >= min_sources
    }
    paths: list[Path] = []
    counts: dict[str, int] = {}
    for label, refs in eligible.items():
        counts[label] = len({(sid, sub) for sid, sub, _p in refs})
        for n, (sid, sub, src) in enumerate(refs):
            if not src.exists():
                continue
            out = root / f"{_safe_label(label)}-src{sid:05d}-sub{sub}-n{n:04d}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.open(src).convert("L").save(out)
            paths.append(out)
    return paths, counts


def _classify(path: Path, models: dict[str, dict[str, object]], max_shift: int, margin_threshold: float):
    match = classify_consensus_models(Image.open(path).convert("L"), models, max_shift=max_shift)
    best, second, margin = match.get("best"), match.get("second"), match.get("margin")
    raw = str(best["character"]) if isinstance(best, dict) else None
    accepted = raw is not None and (margin is None or float(margin) >= margin_threshold)
    return (raw if accepted else "?"), raw, margin, best, second


def main() -> int:
    ap = argparse.ArgumentParser(description="Strict cross-word holdout for mixed-style SAOL glyph and cluster units.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--min-cluster-sources", type=int, default=3)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_words = [w for w in manifest.get("words", []) if isinstance(w, dict)]
    test_words = [w for w in all_words if not args.style or w.get("style") == args.style]
    test_words = test_words[max(0, args.offset):]
    if args.limit > 0:
        test_words = test_words[:args.limit]

    results = []
    skipped = Counter()
    word_correct = unit_correct = unit_total = raw_correct = 0
    glyph_correct = glyph_total = cluster_correct = cluster_total = 0

    with tempfile.TemporaryDirectory(prefix="saol-style-holdout-") as td:
        tmp = Path(td)
        for word in test_words:
            source_id = int(word.get("source_id", -1))
            subnr = word.get("subnr")
            style = str(word.get("style") or "")
            expected_word = str(word.get("expected_word") or "")
            segments = word.get("segments", [])
            if not expected_word or not isinstance(segments, list):
                skipped["missing-metadata"] += 1
                continue

            root = tmp / f"holdout-{source_id:05d}"
            glyph_refs, glyph_sources = _materialize(
                args.library, all_words, style=style, excluded_source=source_id,
                excluded_subnr=subnr, root=root / "glyph", kind="glyph")
            cluster_refs, cluster_sources = _materialize(
                args.library, all_words, style=style, excluded_source=source_id,
                excluded_subnr=subnr, root=root / "cluster", kind="cluster",
                min_sources=args.min_cluster_sources)
            glyph_models = build_consensus(glyph_refs, max_shift=args.max_shift) if glyph_refs else {}
            cluster_models = build_consensus(cluster_refs, max_shift=args.max_shift) if cluster_refs else {}

            rows = []
            pieces = []
            evaluable = True
            local_correct = 0
            local_total = 0
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                kind = str(seg.get("kind") or "")
                truth = str(seg.get("expected_text") or seg.get("character") or "")
                rel = seg.get("file")
                if not truth or not isinstance(rel, str):
                    evaluable = False
                    break
                path = args.library / rel
                if not path.exists():
                    evaluable = False
                    break
                models = glyph_models if kind == "glyph" else cluster_models
                sources = glyph_sources if kind == "glyph" else cluster_sources
                if truth not in sources or truth not in models:
                    rows.append({"kind": kind, "expected": truth, "prediction": "?", "raw_prediction": None,
                                 "status": "missing-class-after-holdout", "independent_sources": sources.get(truth, 0)})
                    pieces.append("?")
                    local_total += 1
                    if kind == "glyph": glyph_total += 1
                    else: cluster_total += 1
                    continue
                pred, raw, margin, best, second = _classify(path, models, args.max_shift, args.margin)
                ok = pred == truth
                local_correct += int(ok)
                local_total += 1
                raw_correct += int(raw == truth)
                if kind == "glyph":
                    glyph_total += 1; glyph_correct += int(ok)
                else:
                    cluster_total += 1; cluster_correct += int(ok)
                pieces.append(pred)
                rows.append({"kind": kind, "expected": truth, "prediction": pred, "raw_prediction": raw,
                             "margin": margin, "best": best, "second": second,
                             "independent_sources": sources.get(truth, 0)})

            if not evaluable or local_total == 0:
                skipped["unevaluable-word"] += 1
                continue
            prediction = "".join(pieces)
            ok_word = prediction == expected_word
            word_correct += int(ok_word)
            unit_correct += local_correct
            unit_total += local_total
            results.append({"source_id": source_id, "page": word.get("page"), "subnr": subnr,
                            "style": style, "expected": expected_word, "prediction": prediction,
                            "correct": ok_word, "unit_correct": local_correct, "unit_total": local_total,
                            "segments": rows})

    out = {
        "library": str(args.library), "style": args.style, "offset": args.offset,
        "requested_limit": args.limit, "tested_words": len(results), "word_correct": word_correct,
        "word_accuracy": round(word_correct / len(results), 4) if results else None,
        "unit_correct": unit_correct, "unit_total": unit_total,
        "unit_accuracy": round(unit_correct / unit_total, 4) if unit_total else None,
        "raw_unit_accuracy": round(raw_correct / unit_total, 4) if unit_total else None,
        "glyph_accuracy": round(glyph_correct / glyph_total, 4) if glyph_total else None,
        "glyph_total": glyph_total,
        "cluster_accuracy": round(cluster_correct / cluster_total, 4) if cluster_total else None,
        "cluster_total": cluster_total,
        "margin_threshold": args.margin, "max_shift": args.max_shift,
        "min_cluster_sources": args.min_cluster_sources,
        "skipped": dict(sorted(skipped.items())), "results": results,
        "notes": {
            "holdout": "held-out source_id and all rows sharing its subnr are excluded from both glyph and cluster references",
            "measurement": "recognition holdout on already-mined topological units; segmentation quality is not scored here",
            "clusters": "a cluster class is usable only when min_cluster_sources independent training sources remain after holdout",
        },
    }
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
