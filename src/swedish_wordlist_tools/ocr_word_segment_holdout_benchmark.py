from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import build_consensus, classify_consensus_models
from .ocr_word_glyph_read import _segment_word


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def _materialize_refs(library: Path, words: list[dict[str, object]], excluded_source_id: int,
                      excluded_subnr: object, root: Path) -> tuple[list[Path], dict[str, int]]:
    refs: list[Path] = []
    by_class_sources: dict[str, set[tuple[object, object]]] = defaultdict(set)
    for row in words:
        source_id = int(row["source_id"])
        subnr = row.get("subnr")
        if source_id == excluded_source_id or subnr == excluded_subnr:
            continue
        for glyph in row.get("glyphs", []):
            if not isinstance(glyph, dict):
                continue
            ch, rel = glyph.get("character"), glyph.get("file")
            if not isinstance(ch, str) or not isinstance(rel, str):
                continue
            src = library / rel
            if not src.exists():
                continue
            out = root / f"{_safe_char(ch)}-src{source_id:05d}-sub{subnr}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.open(src).convert("L").save(out)
            refs.append(out)
            by_class_sources[ch].add((source_id, subnr))
    return refs, {ch: len(v) for ch, v in by_class_sources.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-word holdout benchmark for a mined SAOL word-segment library.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--offset", type=int, default=0, help="Skip this many held-out words before testing")
    ap.add_argument("--limit", type=int, default=0, help="Maximum held-out words after offset; 0 means all")
    ap.add_argument("--token", action="append", default=[], help="Optional expected token filter; repeatable")
    args = ap.parse_args()

    manifest_path = args.library / "manifest-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_words = list(manifest.get("words", []))
    words = all_words
    if args.token:
        wanted = set(args.token)
        words = [w for w in words if w.get("expected_word") in wanted]
    words = words[max(0, args.offset):]
    if args.limit > 0:
        words = words[:args.limit]

    results = []
    skipped = Counter()
    word_correct = char_correct = char_total = raw_char_correct = 0

    with tempfile.TemporaryDirectory(prefix="saol-word-holdout-") as tmp:
        tmp_root = Path(tmp)
        for row in words:
            source_id = int(row["source_id"])
            subnr = row.get("subnr")
            expected = str(row.get("expected_word") or "")
            word_file = row.get("word_file")
            if not expected or not isinstance(word_file, str):
                skipped["missing-metadata"] += 1
                continue
            path = args.library / word_file
            if not path.exists():
                skipped["missing-word-file"] += 1
                continue

            refs, independent = _materialize_refs(args.library, all_words, source_id, subnr,
                                                   tmp_root / f"holdout-{source_id:05d}")
            missing = sorted({ch for ch in expected if ch not in independent})
            if missing:
                skipped["missing-class-after-holdout"] += 1
                continue

            # This is the expensive operation. Build once for this holdout word,
            # then reuse the models for every glyph in that word.
            models = build_consensus(refs, max_shift=args.max_shift)

            img = Image.open(path).convert("L")
            segments = _segment_word(img, len(expected))
            if len(segments) != len(expected):
                skipped["segment-count"] += 1
                continue

            pred_chars, segrows = [], []
            for i, ((_x0, _x1, glyph), truth) in enumerate(zip(segments, expected)):
                match = classify_consensus_models(glyph, models, max_shift=args.max_shift)
                best, second, margin = match.get("best"), match.get("second"), match.get("margin")
                raw = str(best["character"]) if isinstance(best, dict) else None
                accepted = raw is not None and (margin is None or float(margin) >= args.margin)
                pred = raw if accepted else "?"
                pred_chars.append(pred)
                raw_char_correct += int(raw == truth)
                segrows.append({"index": i, "expected": truth, "raw_prediction": raw,
                                "prediction": pred, "margin": margin, "best": best,
                                "second": second, "query_geometry": match.get("query_geometry")})

            prediction = "".join(pred_chars)
            n = sum(a == b for a, b in zip(prediction, expected))
            char_total += len(expected)
            char_correct += n
            ok = prediction == expected
            word_correct += int(ok)
            results.append({"source_id": source_id, "page": row.get("page"), "subnr": subnr,
                            "expected": expected, "prediction": prediction, "correct": ok,
                            "char_correct": n, "char_total": len(expected),
                            "independent_sources_by_class": independent, "segments": segrows})

    payload = {
        "library": str(args.library), "offset": args.offset, "requested_limit": args.limit,
        "tested_words": len(results), "word_correct": word_correct,
        "word_accuracy": round(word_correct / len(results), 4) if results else None,
        "char_correct": char_correct, "char_total": char_total,
        "char_accuracy": round(char_correct / char_total, 4) if char_total else None,
        "raw_char_accuracy": round(raw_char_correct / char_total, 4) if char_total else None,
        "margin_threshold": args.margin, "max_shift": args.max_shift,
        "skipped": dict(sorted(skipped.items())), "results": results,
        "notes": {
            "holdout": "entire test source_id and all rows from the same subnr excluded from references",
            "segmentation": "training glyphs were mined from whole known words; test word uses the same _segment_word routine",
            "classifier": "per-class aligned consensus with geometry prior; consensus is built once per holdout and reused across its glyphs",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
