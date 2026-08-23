from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import build_consensus, classify_consensus_models


def _safe_label(text: str) -> str:
    return "".join(ch if ch.isalnum() else f"u{ord(ch):04x}" for ch in text)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _materialize_trusted(trusted: Path, kind: str, style: str, root: Path) -> list[Path]:
    manifest = _load(trusted / "manifest-trusted-review-library.json")
    out: list[Path] = []
    for word in manifest.get("words", []):
        if not isinstance(word, dict) or word.get("style") != style:
            continue
        for unit in word.get("units", []):
            if not isinstance(unit, dict) or unit.get("kind") != kind:
                continue
            text, rel = unit.get("text"), unit.get("file")
            if not isinstance(text, str) or not isinstance(rel, str):
                continue
            src = trusted / rel
            if not src.exists():
                continue
            dst = root / f"{_safe_label(text)}-src{word.get('source_id')}-{len(out):05d}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            Image.open(src).convert("L").save(dst)
            out.append(dst)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank unreviewed SAOL glyph/cluster candidates against a manually trusted library.")
    ap.add_argument("library", type=Path, help="Original mixed-style word segment library")
    ap.add_argument("trusted", type=Path, help="Trusted review library")
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--min-margin", type=float, default=0.02)
    ap.add_argument("--max-score", type=float, default=0.45)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    source_manifest = _load(args.library / "manifest-style-word-segments.json")
    trusted_manifest = _load(args.trusted / "manifest-trusted-review-library.json")
    trusted_sources = {int(w.get("source_id", -1)) for w in trusted_manifest.get("words", []) if isinstance(w, dict)}

    models: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
    with tempfile.TemporaryDirectory(prefix="saol-trusted-candidate-") as td:
        root = Path(td)
        for style in ("roman", "italic"):
            for kind in ("glyph", "cluster"):
                refs = _materialize_trusted(args.trusted, kind, style, root / style / kind)
                models[(style, kind)] = build_consensus(refs, max_shift=args.max_shift) if refs else {}

        rows: list[dict[str, object]] = []
        for word in source_manifest.get("words", []):
            if not isinstance(word, dict):
                continue
            source_id = int(word.get("source_id", -1))
            if source_id in trusted_sources:
                continue
            style = str(word.get("style") or "")
            if style not in {"roman", "italic"}:
                continue
            for seg in word.get("segments", []):
                if not isinstance(seg, dict):
                    continue
                kind = str(seg.get("kind") or "glyph")
                truth = str(seg.get("expected_text") or seg.get("character") or "")
                rel = seg.get("file")
                if kind not in {"glyph", "cluster"} or not truth or not isinstance(rel, str):
                    continue
                path = args.library / rel
                if not path.exists():
                    continue
                mm = models.get((style, kind), {})
                if truth not in mm:
                    continue
                match = classify_consensus_models(Image.open(path).convert("L"), mm, max_shift=args.max_shift)
                best = match.get("best")
                second = match.get("second")
                margin = match.get("margin")
                if not isinstance(best, dict):
                    continue
                raw = str(best.get("character"))
                score = float(best.get("score", 9.0))
                if raw != truth or (margin is not None and float(margin) < args.min_margin) or score > args.max_score:
                    continue
                rows.append({
                    "source_id": source_id, "style": style, "page": word.get("page"), "column": word.get("column"),
                    "subnr": word.get("subnr"), "headword": word.get("headword"), "expected_word": word.get("expected_word"),
                    "word_file": word.get("word_file"), "kind": kind, "index": seg.get("index"), "truth": truth,
                    "segment_file": rel, "score": round(score, 6), "margin": margin, "best": best, "second": second,
                })

    rows.sort(key=lambda r: (float(r["score"]), -float(r["margin"] if r["margin"] is not None else 9.0), int(r["source_id"]), int(r.get("index") or 0)))
    if args.limit > 0:
        rows = rows[:args.limit]
    out = {
        "library": str(args.library), "trusted": str(args.trusted), "candidate_count": len(rows),
        "min_margin": args.min_margin, "max_score": args.max_score, "max_shift": args.max_shift, "candidates": rows,
        "notes": {"policy": "only candidates whose trusted-model best class equals facit and clears score/margin thresholds are shown", "review": "candidate images and word images are exact files used by matching/mining"},
    }
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
