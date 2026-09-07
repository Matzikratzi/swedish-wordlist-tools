from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .ocr_glyph_consensus_match import build_consensus


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build per-character SAOL consensus glyphs from benchmark-verified source words."
    )
    ap.add_argument("library", type=Path, help="Mined word-segment library")
    ap.add_argument(
        "benchmarks",
        nargs="+",
        type=Path,
        help="One or more holdout benchmark JSON files; only correct words are trusted",
    )
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--min-sources", type=int, default=2)
    args = ap.parse_args()

    manifest_path = args.library / "manifest-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    for benchmark_path in args.benchmarks:
        if not benchmark_path.exists():
            raise SystemExit(f"missing {benchmark_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trusted_ids: set[int] = set()
    benchmark_summaries = []
    for benchmark_path in args.benchmarks:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        accepted = {
            int(row["source_id"])
            for row in benchmark.get("results", [])
            if isinstance(row, dict) and row.get("correct") is True and "source_id" in row
        }
        trusted_ids.update(accepted)
        benchmark_summaries.append({
            "file": str(benchmark_path),
            "tested_words": benchmark.get("tested_words"),
            "word_accuracy": benchmark.get("word_accuracy"),
            "accepted_source_count": len(accepted),
            "accepted_source_ids": sorted(accepted),
        })

    if not trusted_ids:
        raise SystemExit("benchmarks contain no correct/trusted source_id values")

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
        "benchmarks": benchmark_summaries,
        "trusted_source_count": len(trusted_ids),
        "trusted_source_ids": sorted(trusted_ids),
        "max_shift": args.max_shift,
        "min_sources": args.min_sources,
        "model_count": len(rows),
        "missing_manifest_sources": missing_sources,
        "missing_glyph_files": missing_files,
        "models": rows,
        "notes": {
            "selection": "union of source words marked correct by the supplied holdout benchmark files",
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
