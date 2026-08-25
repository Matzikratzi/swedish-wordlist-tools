from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FORMAT = "saol14-manual-glyph-facit-v1"


def _shape_from_annotation(word: dict[str, Any], ann: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    rel = ann.get("pixels_relative_to_baseline")
    if not isinstance(rel, list):
        baseline = int(word.get("baseline_y") or 0)
        pixels = ann.get("pixels") or []
        rel = [[int(x), int(y) - baseline] for x, y in pixels]
    pts = [(int(x), int(y)) for x, y in rel]
    if not pts:
        return ()
    min_x = min(x for x, _ in pts)
    return tuple(sorted((x - min_x, y) for x, y in pts))


def _source(word: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_word": word.get("expected_word"),
        "page": word.get("page"),
        "subnr": word.get("subnr"),
        "source_id": word.get("source_id"),
        "word_file": word.get("word_file"),
    }


def _source_key(src: dict[str, Any]) -> tuple[Any, ...]:
    return (src.get("source_id"), src.get("word_file"), src.get("expected_word"), src.get("page"), src.get("subnr"))


def _load_existing(path: Path | None) -> dict[tuple[str, str, tuple[tuple[int, int], ...]], list[dict[str, Any]]]:
    out: dict[tuple[str, str, tuple[tuple[int, int], ...]], list[dict[str, Any]]] = defaultdict(list)
    if path is None or not path.exists():
        return out
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT:
        raise SystemExit(f"unsupported facit format in {path}: {payload.get('format')!r}")
    for glyph in payload.get("glyphs", []):
        label = str(glyph.get("label") or "")
        style = str(glyph.get("style") or "roman")
        shape = tuple((int(x), int(y)) for x, y in glyph.get("pixels_relative_to_baseline", []))
        if not label or not shape:
            continue
        out[(label, style, shape)].extend(glyph.get("sources") or [])
    return out


def build(input_path: Path, existing_path: Path | None = None) -> dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    words = payload.get("words") or []
    if not isinstance(words, list):
        raise SystemExit("input has no words list")

    glyphs = _load_existing(existing_path)
    manual_annotations = 0
    skipped_empty = 0

    for word in words:
        if not isinstance(word, dict):
            continue
        # Old hidden style-copy rows are editor artefacts, never independent truth.
        if "::stylecopy" in str(word.get("source_id") or ""):
            continue
        default_style = str(word.get("style") or "roman")
        for ann in word.get("annotations") or []:
            if not isinstance(ann, dict) or ann.get("candidate_status") != "manual":
                continue
            manual_annotations += 1
            label = str(ann.get("label") or "").strip()
            style = str(ann.get("style") or default_style)
            shape = _shape_from_annotation(word, ann)
            if not label or not shape:
                skipped_empty += 1
                continue
            key = (label, style, shape)
            src = _source(word)
            known = {_source_key(s) for s in glyphs[key]}
            if _source_key(src) not in known:
                glyphs[key].append(src)

    rows = []
    for (label, style, shape), sources in sorted(glyphs.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        rows.append({
            "label": label,
            "style": style,
            "pixels_relative_to_baseline": [[x, y] for x, y in shape],
            "sources": sorted(sources, key=lambda s: (int(s.get("page") or 0), str(s.get("source_id") or ""))),
        })

    return {
        "format": FORMAT,
        "coordinate_system": "glyph x normalized to leftmost ink; y relative to support baseline",
        "policy": "manual annotations only; exact duplicate label/style/shapes merged; source provenance retained",
        "glyphs": rows,
        "stats": {
            "input_words": len(words),
            "manual_annotations_seen": manual_annotations,
            "unique_label_style_shapes": len(rows),
            "skipped_empty": skipped_empty,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract/merge canonical manually identified SAOL glyph shapes from an editor atlas.")
    ap.add_argument("input", type=Path)
    ap.add_argument("--existing", type=Path, help="existing canonical facit to merge into")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    result = build(args.input, args.existing)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats = result["stats"]
    print(f"input_words={stats['input_words']} manual={stats['manual_annotations_seen']} unique_shapes={stats['unique_label_style_shapes']} skipped_empty={stats['skipped_empty']}")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
