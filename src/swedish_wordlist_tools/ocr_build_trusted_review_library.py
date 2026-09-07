from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_label(text: str) -> str:
    return "".join(ch if ch.isalnum() else f"u{ord(ch):04x}" for ch in text)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a conservative trusted glyph/cluster library from reviewed SAOL segments."
    )
    ap.add_argument("library", type=Path, help="Source mixed-style word-segment library")
    ap.add_argument("feedback", type=Path, help="Exported holdout-review feedback JSON")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = _load_json(manifest_path)
    feedback = _load_json(args.feedback)

    feedback_words = {
        int(w["source_id"]): w
        for w in feedback.get("words", [])
        if isinstance(w, dict) and str(w.get("source_id", "")).lstrip("-").isdigit()
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "glyphs").mkdir(exist_ok=True)
    (args.out_dir / "clusters").mkdir(exist_ok=True)
    (args.out_dir / "words").mkdir(exist_ok=True)

    stats = Counter()
    glyph_counts: dict[str, Counter[str]] = defaultdict(Counter)
    cluster_counts: dict[str, Counter[str]] = defaultdict(Counter)
    trusted_words: list[dict[str, object]] = []

    for word in manifest.get("words", []):
        if not isinstance(word, dict):
            continue
        source_id = int(word.get("source_id", -1))
        review = feedback_words.get(source_id)
        if review is None:
            stats["words-unreviewed"] += 1
            continue
        if review.get("word_status") != "ok":
            stats["words-rejected"] += 1
            continue

        style = str(word.get("style") or "")
        expected_word = str(word.get("expected_word") or "")
        review_units = {
            int(u["index"]): str(u.get("status") or "")
            for u in review.get("units", [])
            if isinstance(u, dict) and str(u.get("index", "")).lstrip("-").isdigit()
        }
        segments = [s for s in word.get("segments", []) if isinstance(s, dict)]
        accepted_units: list[dict[str, object]] = []

        for seg in segments:
            index = int(seg.get("index", -1))
            if review_units.get(index) != "ok":
                stats["units-rejected"] += 1
                continue
            rel = seg.get("file")
            if not isinstance(rel, str):
                stats["units-missing-file"] += 1
                continue
            src = args.library / rel
            if not src.exists():
                stats["units-missing-file"] += 1
                continue

            kind = str(seg.get("kind") or "glyph")
            text = str(seg.get("expected_text") or seg.get("character") or "")
            if not text:
                stats["units-missing-label"] += 1
                continue

            safe = _safe_label(text)
            if kind == "cluster":
                n = cluster_counts[style][text]
                dst_rel = Path("clusters") / style / f"{safe}-{n:05d}-src{source_id:05d}.png"
                cluster_counts[style][text] += 1
                stats["clusters-trusted"] += 1
            else:
                n = glyph_counts[style][text]
                dst_rel = Path("glyphs") / style / f"{safe}-{n:05d}-src{source_id:05d}.png"
                glyph_counts[style][text] += 1
                stats["glyphs-trusted"] += 1

            dst = args.out_dir / dst_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            accepted_units.append({
                "kind": kind,
                "text": text,
                "index": index,
                "file": str(dst_rel),
                "source_file": rel,
            })

        if not accepted_units:
            stats["words-with-no-trusted-units"] += 1
            continue

        word_rel = word.get("word_file")
        copied_word = None
        if isinstance(word_rel, str):
            src_word = args.library / word_rel
            if src_word.exists():
                dst_rel = Path("words") / Path(word_rel).name
                shutil.copy2(src_word, args.out_dir / dst_rel)
                copied_word = str(dst_rel)

        trusted_words.append({
            "source_id": source_id,
            "style": style,
            "page": word.get("page"),
            "column": word.get("column"),
            "subnr": word.get("subnr"),
            "expected_word": expected_word,
            "word_file": copied_word,
            "units": accepted_units,
        })
        stats["words-trusted"] += 1

    glyph_sources: dict[str, dict[str, int]] = {}
    cluster_sources: dict[str, dict[str, int]] = {}
    for style in sorted(set(glyph_counts) | set(cluster_counts)):
        glyph_sources[style] = dict(sorted(glyph_counts[style].items()))
        cluster_sources[style] = dict(sorted(cluster_counts[style].items()))

    out = {
        "source_library": str(args.library),
        "feedback": str(args.feedback),
        "word_count": len(trusted_words),
        "stats": dict(sorted(stats.items())),
        "glyph_counts": glyph_sources,
        "cluster_counts": cluster_sources,
        "words": trusted_words,
        "notes": {
            "policy": "only word_status=ok and unit status=ok are retained",
            "purpose": "high-precision training library; ambiguous or badly cropped material is excluded rather than repaired",
            "source_preservation": "copied units retain source_id/subnr/page metadata for future holdout and provenance checks",
        },
    }
    out_path = args.out_dir / "manifest-trusted-review-library.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
