from __future__ import annotations

import argparse
import json
from pathlib import Path


def _key(word: dict[str, object]) -> tuple[str, ...]:
    sid = str(word.get("source_id") or "")
    if sid:
        return ("source_id", sid)
    wf = str(word.get("word_file") or "")
    if wf:
        return ("word_file", wf)
    return (
        "fallback",
        str(word.get("page") or ""),
        str(word.get("subnr") or ""),
        str(word.get("expected_word") or ""),
        str(word.get("style") or ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge a base manual pixel atlas with later correction/exception exports; later files replace the same word and add new words.")
    ap.add_argument("atlases", nargs="+", type=Path, help="Oldest first, newest last")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    merged: dict[tuple[str, ...], dict[str, object]] = {}
    order: list[tuple[str, ...]] = []
    formats: list[str] = []
    for path in args.atlases:
        payload = json.loads(path.read_text(encoding="utf-8"))
        formats.append(str(payload.get("format") or ""))
        for raw in payload.get("words", []):
            if not isinstance(raw, dict):
                continue
            key = _key(raw)
            if key not in merged:
                order.append(key)
            merged[key] = raw

    words = [merged[k] for k in order]
    out = {
        "format": "saol-manual-pixel-atlas-merged-v1",
        "coordinate_system": "original word crop origin top-left; y_rel = y - baseline_y",
        "source_formats": formats,
        "source_files": [str(p) for p in args.atlases],
        "word_count": len(words),
        "words": words,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    print(f"words={len(words)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
