from __future__ import annotations

"""Capture a reproducible baseline from the conservative SAOL14 OCR scanner."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from . import ocr_find_unreviewed_glyph_rows as scanner
from . import ocr_find_unreviewed_glyph_rows_conservative as conservative
from .ocr_glyph_facit_store import load_split_facit, verify_facit

FORMAT = "saol14-ocr-conservative-baseline-v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(_sha256_file(item).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _match_record(match) -> dict:
    pixels = tuple(sorted((int(x) - int(match.x), int(y) - int(match.baseline)) for x, y in match.pixels))
    raster = json.dumps(pixels, separators=(",", ":")).encode()
    return {"label": str(match.label), "style": str(match.style), "x": int(match.x), "baseline": int(match.baseline), "model_pixels": len(pixels), "raster_sha256": hashlib.sha256(raster).hexdigest(), "sources": int(getattr(match, "sources", 0) or 0)}


def _row_record(page: int, position: tuple[int, int], state: dict) -> dict:
    work = scanner.classify_row_state(page, position, state)
    matches = list(state.get("matches") or [])
    matches.sort(key=lambda m: (int(m.x), int(m.baseline), str(m.label), str(m.style)))
    return {"page": int(page), "column": int(position[0]), "row": int(position[1]), "crop_box": [int(v) for v in state.get("crop_box") or ()], "baseline": None if state.get("baseline") is None else int(state["baseline"]), "covered_pixels": work.covered_pixels, "source_pixels": work.source_pixels, "fully_exact": work.fully_exact, "needs_work": work.needs_work, "unreviewed_matches": work.unreviewed_matches, "text": str(state.get("text") or ""), "matches": [_match_record(m) for m in matches]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture conservative OCR output as a frozen baseline")
    ap.add_argument("jsonl", type=Path); ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--start-page", type=int, required=True); ap.add_argument("--end-page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210); ap.add_argument("--expect-facit-models", type=int)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    split = args.facit.parent / "facit-v2"
    verify_facit(args.facit, split)
    facit_payload = load_split_facit(split)
    model_count = len(facit_payload.get("models") or [])
    if args.expect_facit_models is not None and model_count != args.expect_facit_models:
        raise ValueError(f"expected {args.expect_facit_models} facit models, got {model_count}")

    out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    rows_path, problems_path, summary_path = out / "rows.jsonl", out / "problems.json", out / "summary.json"
    rows_fh = rows_path.open("w", encoding="utf-8"); all_rows, problems = [], []
    original_classify = scanner.classify_row_state

    def capture(page, position, state):
        work = original_classify(page, position, state); record = _row_record(page, position, state)
        rows_fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"); all_rows.append(record)
        if work.needs_work: problems.append(record)
        return work

    scanner.classify_row_state = capture; old_argv = sys.argv
    sys.argv = [old_argv[0], str(args.jsonl), "--facit", str(args.facit), "--start-page", str(args.start_page), "--end-page", str(args.end_page), "--threshold", str(args.threshold)]
    try: result = conservative.main()
    finally:
        scanner.classify_row_state = original_classify; sys.argv = old_argv; rows_fh.close()

    summary = {"format": "saol14-ocr-baseline-summary-v1", "pages": args.end_page - args.start_page + 1, "rows": len(all_rows), "exact": sum(bool(r["fully_exact"]) for r in all_rows), "needs_work": len(problems), "facit_models": model_count}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    problems_path.write_text(json.dumps({"format": "saol14-ocr-baseline-problems-v1", "rows": problems}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"format": FORMAT, "algorithm": "ocr_find_unreviewed_glyph_rows_conservative", "git_commit": _git_commit(), "parameters": {"start_page": args.start_page, "end_page": args.end_page, "threshold": args.threshold}, "source": {"jsonl": str(args.jsonl), "sha256": _sha256_file(args.jsonl)}, "facit": {"aggregate": str(args.facit), "aggregate_sha256": _sha256_file(args.facit), "split_store": str(split), "split_store_sha256": _sha256_tree(split), "models": model_count, "verified_equal": True}, "outputs": {name: {"path": path.name, "sha256": _sha256_file(path)} for name, path in (("rows", rows_path), ("problems", problems_path), ("summary", summary_path))}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"baseline: pages={summary['pages']} rows={summary['rows']} exact={summary['exact']}/{summary['rows']} needs_work={summary['needs_work']} facit_models={model_count}")
    print(f"baseline: saved to {out}"); return result


if __name__ == "__main__": raise SystemExit(main())
