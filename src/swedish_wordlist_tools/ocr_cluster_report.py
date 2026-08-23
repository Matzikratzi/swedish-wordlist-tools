from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _load_manifest(library: Path) -> dict[str, object]:
    path = library / "manifest-style-word-segments.json"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Report recurring unsplittable SAOL OCR clusters by style/text.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--min-sources", type=int, default=1)
    args = ap.parse_args()

    payload = _load_manifest(args.library)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)

    for word in payload.get("words", []):
        if not isinstance(word, dict):
            continue
        style = str(word.get("style") or "")
        source_id = word.get("source_id")
        for seg in word.get("segments", []):
            if not isinstance(seg, dict) or seg.get("kind") != "cluster":
                continue
            text = str(seg.get("expected_text") or "")
            rel = seg.get("file")
            if not text or not isinstance(rel, str):
                continue
            grouped[(style, text)].append({
                "source_id": source_id,
                "subnr": word.get("subnr"),
                "page": word.get("page"),
                "column": word.get("column"),
                "expected_word": word.get("expected_word"),
                "file": rel,
            })

    rows = []
    for (style, text), refs in grouped.items():
        source_ids = {str(r.get("source_id")) for r in refs}
        if len(source_ids) < args.min_sources:
            continue
        rows.append({
            "style": style,
            "text": text,
            "reference_count": len(refs),
            "independent_source_count": len(source_ids),
            "references": refs,
        })

    rows.sort(key=lambda r: (-int(r["independent_source_count"]), str(r["style"]), str(r["text"])))
    out = {
        "library": str(args.library),
        "min_sources": args.min_sources,
        "cluster_class_count": len(rows),
        "cluster_reference_count": sum(int(r["reference_count"]) for r in rows),
        "clusters": rows,
    }
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
