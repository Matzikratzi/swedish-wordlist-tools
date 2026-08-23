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


def _trusted_counts(manifest: dict[str, object]) -> dict[tuple[str, str, str], int]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for word in manifest.get("words", []):
        if not isinstance(word, dict):
            continue
        style = str(word.get("style") or "")
        for unit in word.get("units", []):
            if not isinstance(unit, dict):
                continue
            kind = str(unit.get("kind") or "glyph")
            text = str(unit.get("text") or "")
            if style and kind and text:
                counts[(style, kind, text)] += 1
    return dict(counts)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rank unreviewed SAOL glyph/cluster candidates for human promotion into the trusted library."
    )
    ap.add_argument("library", type=Path, help="Original mixed-style word segment library")
    ap.add_argument("trusted", type=Path, help="Trusted review library")
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--min-margin", type=float, default=0.02,
                    help="Strict-mode minimum classifier margin")
    ap.add_argument("--max-score", type=float, default=0.45,
                    help="Strict-mode maximum best score")
    ap.add_argument("--strict", action="store_true",
                    help="Old behavior: only show candidates already classified correctly above thresholds")
    ap.add_argument("--limit-per-class", type=int, default=12,
                    help="Maximum candidates per style/kind/facit class; prevents . or pl. from dominating")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    source_manifest = _load(args.library / "manifest-style-word-segments.json")
    trusted_manifest = _load(args.trusted / "manifest-trusted-review-library.json")
    trusted_sources = {
        int(w.get("source_id", -1))
        for w in trusted_manifest.get("words", [])
        if isinstance(w, dict)
    }
    trusted_counts = _trusted_counts(trusted_manifest)

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
                best = second = None
                raw = None
                margin = None
                best_score = None
                truth_score = None
                truth_rank = None
                model_status = "unseen-class"

                if mm:
                    match = classify_consensus_models(
                        Image.open(path).convert("L"), mm, max_shift=args.max_shift
                    )
                    best = match.get("best")
                    second = match.get("second")
                    margin = match.get("margin")
                    ranked = match.get("ranked") if isinstance(match.get("ranked"), list) else []
                    if isinstance(best, dict):
                        raw = str(best.get("character"))
                        best_score = float(best.get("score", 9.0))
                    for rank, item in enumerate(ranked, 1):
                        if isinstance(item, dict) and str(item.get("character")) == truth:
                            truth_rank = rank
                            truth_score = float(item.get("score", 9.0))
                            break
                    if truth in mm:
                        model_status = "facit-modelled"
                    else:
                        model_status = "unseen-class"

                if args.strict:
                    if raw != truth:
                        continue
                    if margin is not None and float(margin) < args.min_margin:
                        continue
                    if best_score is None or best_score > args.max_score:
                        continue

                rows.append({
                    "source_id": source_id,
                    "style": style,
                    "page": word.get("page"),
                    "column": word.get("column"),
                    "subnr": word.get("subnr"),
                    "headword": word.get("headword"),
                    "expected_word": word.get("expected_word"),
                    "word_file": word.get("word_file"),
                    "kind": kind,
                    "index": seg.get("index"),
                    "truth": truth,
                    "segment_file": rel,
                    "trusted_count": trusted_counts.get((style, kind, truth), 0),
                    "model_status": model_status,
                    "raw_prediction": raw,
                    "best_score": round(best_score, 6) if best_score is not None else None,
                    "truth_score": round(truth_score, 6) if truth_score is not None else None,
                    "truth_rank": truth_rank,
                    "margin": margin,
                    "best": best,
                    "second": second,
                })

    # Prefer classes with little/no trusted material. Within a class, put candidates
    # whose facit model already resembles them near the top, but never hide a clean
    # topological candidate merely because the current classifier dislikes it.
    rows.sort(key=lambda r: (
        int(r.get("trusted_count") or 0),
        0 if r.get("truth_rank") == 1 else (1 if r.get("truth_rank") is not None else 2),
        float(r["truth_score"]) if r.get("truth_score") is not None else 9.0,
        int(r["source_id"]),
        int(r.get("index") or 0),
    ))

    kept: list[dict[str, object]] = []
    per_class: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        key = (str(row["style"]), str(row["kind"]), str(row["truth"]))
        if args.limit_per_class > 0 and per_class[key] >= args.limit_per_class:
            continue
        per_class[key] += 1
        kept.append(row)
        if args.limit > 0 and len(kept) >= args.limit:
            break

    out = {
        "library": str(args.library),
        "trusted": str(args.trusted),
        "candidate_count": len(kept),
        "strict": args.strict,
        "min_margin": args.min_margin,
        "max_score": args.max_score,
        "limit_per_class": args.limit_per_class,
        "max_shift": args.max_shift,
        "candidates": kept,
        "notes": {
            "policy": "default broad mode shows all exact-facit topological units; classifier confidence only ranks candidates",
            "strict_policy": "--strict restores the former best-class/score/margin filtering",
            "diversity": "limit-per-class prevents frequent punctuation and pl. material from monopolizing review",
            "review": "candidate images and word images are exact files used by matching/mining",
        },
    }
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
