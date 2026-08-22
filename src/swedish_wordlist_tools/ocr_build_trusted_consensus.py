from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import build_consensus


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build per-character SAOL consensus glyphs from benchmark-verified source words."
    )
    ap.add_argument("library", type=Path, help="Mined word-segment library")
    ap.add_argument("benchmark", type=Path, help="Holdout benchmark JSON; only correct words are trusted")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--min-sources", type=int, default=2)
    args = ap.parse_args()

    manifest_path = args.library / "manifest-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    if not args.benchmark.exists():
        raise SystemExit(f"missing {args.benchmark}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))

    trusted_ids = {
        int(row["source_id"])
        for row in benchmark.get("results", [])
        if isinstance(row, dict) and row.get("correct") is True and "source_id" in row
    }
    if not trusted_ids:
        raise SystemExit("benchmark contains no correct/trusted source_id values")

    word_by_id = {
        int(row["source_id"]): row
        for row in manifest.get("words", [])
        if isinstance(row, dict) and "source_id" in row
    }

    refs: list[Path] = []
    sources_by_char: dict[str, set[int]] = defaultdict(set)
    missing_files = 0
    missing_sources = 0

    for source_id in sorted(trusted_ids):
        row = word_by_id.get(source_id)
        if row is None:
            missing_sources += 1
            continue
        for glyph in row.get("glyphs", []):
            if not isinstance(glyph, dict):
                continue
            ch = glyph.get("character")
            rel = glyph.get("file")
            if not isinstance(ch, str) or not isinstance(rel, str):
                continue
            path = args.library / rel
            if not path.exists():
                missing_files += 1
                continue
            refs.append(path)
            sources_by_char[ch].add(source_id)

    models = build_consensus(refs, max_shift=args.max_shift)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for ch in sorted(models):
        model = models[ch]
        source_ids = sorted(sources_by_char.get(ch, set()))
        if len(source_ids) < args.min_sources:
            continue
        stem = _safe_char(ch)
        median_file = f"{stem}-median.png"
        mask_file = f"{stem}-variation-mask.png"
        # build_consensus returns inverted-ink grayscale models: black background,
        # brighter ink. Save them directly for inspection and matching.
        model["median"].save(args.out_dir / median_file)
        model["mask"].save(args.out_dir / mask_file)
        rows.append({
            "character": ch,
            "median_file": median_file,
            "variation_mask_file": mask_file,
            "reference_count": int(model["count"]),
            "independent_source_count": len(source_ids),
            "source_ids": source_ids,
            "geometry": model["geometry"],
            "rejected_reference_count": len(model.get("rejected_templates", [])),
            "rejected_templates": list(model.get("rejected_templates", [])),
        })

    payload = {
        "library": str(args.library),
        "benchmark": str(args.benchmark),
        "trusted_source_count": len(trusted_ids),
        "trusted_source_ids": sorted(trusted_ids),
        "max_shift": args.max_shift,
        "min_sources": args.min_sources,
        "model_count": len(rows),
        "missing_manifest_sources": missing_sources,
        "missing_glyph_files": missing_files,
        "models": rows,
        "notes": {
            "selection": "only source words marked correct by the supplied holdout benchmark",
            "alignment": "translation only; no scaling or stretching",
            "median": "pixel median after alignment",
            "variation_mask": "stable glyph-support pixels receive higher weight; variable raster artifacts lower weight",
        },
    }
    manifest_out = args.out_dir / "manifest-consensus.json"
    manifest_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
