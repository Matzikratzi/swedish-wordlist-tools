from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import (
    _common_canvas,
    _geometry_from_ink,
    _horizontal_support,
    _median,
    _medoid,
    _best_aligned,
    _stability_mask,
)


def _safe_label(text: str) -> str:
    return "".join(ch if ch.isalnum() else f"u{ord(ch):04x}" for ch in text)


def _load_manifest(library: Path) -> dict[str, object]:
    path = library / "manifest-style-word-segments.json"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build trusted consensus images for recurring unsplittable SAOL clusters.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--min-sources", type=int, default=3)
    ap.add_argument("--max-shift", type=int, default=3)
    args = ap.parse_args()

    payload = _load_manifest(args.library)
    grouped: dict[tuple[str, str], list[tuple[str, Path, dict[str, object]]]] = defaultdict(list)

    for word in payload.get("words", []):
        if not isinstance(word, dict):
            continue
        style = str(word.get("style") or "")
        source_id = str(word.get("source_id"))
        for seg in word.get("segments", []):
            if not isinstance(seg, dict) or seg.get("kind") != "cluster":
                continue
            text = str(seg.get("expected_text") or "")
            rel = seg.get("file")
            if not text or not isinstance(rel, str):
                continue
            path = args.library / rel
            if not path.exists():
                continue
            grouped[(style, text)].append((source_id, path, {
                "source_id": word.get("source_id"),
                "subnr": word.get("subnr"),
                "page": word.get("page"),
                "column": word.get("column"),
                "expected_word": word.get("expected_word"),
                "file": rel,
            }))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    models: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for (style, text), refs in sorted(grouped.items()):
        source_count = len({source_id for source_id, _path, _meta in refs})
        if source_count < args.min_sources:
            skipped.append({"style": style, "text": text, "independent_source_count": source_count})
            continue

        accepted: list[tuple[Path, Image.Image, dict[str, object]]] = []
        rejected: list[str] = []
        for _source_id, path, meta in refs:
            support = _horizontal_support(Image.open(path).convert("L"))
            if support is None:
                rejected.append(str(path.relative_to(args.library)))
            else:
                accepted.append((path, support, meta))
        accepted_sources = {str(meta.get("source_id")) for _p, _im, meta in accepted}
        if len(accepted_sources) < args.min_sources:
            skipped.append({
                "style": style, "text": text,
                "independent_source_count": source_count,
                "accepted_independent_source_count": len(accepted_sources),
                "reason": "too-few-usable-images",
            })
            continue

        raw = [im for _p, im, _meta in accepted]
        anchor = _medoid(raw, args.max_shift)
        aligned = _common_canvas([_best_aligned(im, anchor, args.max_shift) for im in raw])
        median = _median(aligned)
        mask = _stability_mask(aligned, median)
        bbox = median.getbbox()
        if bbox:
            median = median.crop(bbox)
            mask = mask.crop(bbox)

        model_dir = args.out_dir / style
        model_dir.mkdir(parents=True, exist_ok=True)
        stem = _safe_label(text)
        median_rel = Path(style) / f"{stem}-median.png"
        mask_rel = Path(style) / f"{stem}-variation-mask.png"
        median.save(args.out_dir / median_rel)
        mask.save(args.out_dir / mask_rel)

        models.append({
            "style": style,
            "text": text,
            "reference_count": len(accepted),
            "independent_source_count": len(accepted_sources),
            "rejected_reference_count": len(rejected),
            "geometry": _geometry_from_ink(median),
            "median_file": str(median_rel),
            "variation_mask_file": str(mask_rel),
            "references": [meta for _p, _im, meta in accepted],
            "rejected_files": rejected,
        })

    out = {
        "library": str(args.library),
        "min_sources": args.min_sources,
        "max_shift": args.max_shift,
        "model_count": len(models),
        "models": models,
        "skipped": skipped,
        "notes": {
            "promotion": "clusters require min_sources independent word sources after image validation",
            "use": "cluster models are fallback OCR units only when strict topology cannot split a component",
            "alignment": "translation only; no scaling or stretching",
        },
    }
    manifest = args.out_dir / "manifest-cluster-consensus.json"
    manifest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(out, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
