#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from time import perf_counter

from swedish_wordlist_tools.ocr_glyph_review_delete import load_facit_with_typography
from swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _match_record(match) -> dict:
    return {
        "label": match.label,
        "style": match.style,
        "x": int(match.x),
        "baseline": int(match.baseline),
        "model_pixels": int(match.model_pixels),
        "sources": list(match.sources),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export a reproducible exact-glyph OCR reference page with timing metadata."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output-dir", type=Path, default=Path("tests/reference/saol14-ocr"))
    args = ap.parse_args()

    total_started = perf_counter()
    models = load_facit_with_typography(args.facit)

    prepare_started = perf_counter()
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    prepare_seconds = perf_counter() - prepare_started
    context["quiet_successful_ownership"] = True

    # First pass lets page-global ownership refinements settle before export.
    settle_started = perf_counter()
    for position in context["positions"]:
        load_review_state_pixel_array(context, position, models)
    settle_seconds = perf_counter() - settle_started

    rows: list[dict] = []
    row_timings: list[dict] = []
    export_started = perf_counter()
    for column, row in context["positions"]:
        row_started = perf_counter()
        state = load_review_state_pixel_array(context, (column, row), models)
        elapsed = perf_counter() - row_started
        matches = sorted(
            state.get("matches") or [],
            key=lambda m: (m.x, m.baseline, m.label, m.style),
        )
        rows.append(
            {
                "page": int(args.page),
                "column": int(column),
                "row": int(row),
                "text": state.get("text", ""),
                "baseline": state.get("baseline"),
                "covered_pixels": int(state.get("covered_pixels") or 0),
                "source_pixels": int(state.get("source_pixels") or 0),
                "fully_exact": bool(state.get("fully_exact", False)),
                "glyphs": [_match_record(match) for match in matches],
            }
        )
        row_timings.append(
            {"column": int(column), "row": int(row), "seconds": elapsed}
        )
    export_seconds = perf_counter() - export_started
    total_seconds = perf_counter() - total_started

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"page-{args.page:03d}"
    reference_path = args.output_dir / f"{stem}.jsonl"
    meta_path = args.output_dir / f"{stem}.meta.json"

    with reference_path.open("w", encoding="utf-8") as fh:
        for item in rows:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    slowest = sorted(row_timings, key=lambda item: item["seconds"], reverse=True)[:10]
    metadata = {
        "format": "saol14-ocr-reference-v1",
        "page": int(args.page),
        "row_count": len(rows),
        "all_rows_fully_exact": all(row["fully_exact"] for row in rows),
        "source_jsonl": str(args.jsonl),
        "threshold": int(args.threshold),
        "generator_git_commit": _git_head(),
        "facit_path": str(args.facit),
        "facit_sha256": _sha256(args.facit),
        "timing_seconds": {
            "page_prepare": prepare_seconds,
            "glyph_analysis_settle_pass": settle_seconds,
            "reference_export_pass": export_seconds,
            "total": total_seconds,
        },
        "slowest_export_rows": slowest,
    }
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"reference: {reference_path}")
    print(f"metadata:  {meta_path}")
    print(
        f"rows={len(rows)} exact={metadata['all_rows_fully_exact']} "
        f"prepare={prepare_seconds:.3f}s settle={settle_seconds:.3f}s "
        f"export={export_seconds:.3f}s total={total_seconds:.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
