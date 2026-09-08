from __future__ import annotations

"""Capture a deterministic baseline from the existing conservative OCR command.

This module deliberately does not reimplement or wrap any OCR decisions.  It
runs ``ocr_find_unreviewed_glyph_rows_conservative.main`` unchanged and observes
rows at the common ``scanner.classify_row_state`` boundary.  The resulting
baseline therefore records the exact behaviour of the conservative scanner,
including rows that are currently wrong or incomplete.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from . import ocr_find_unreviewed_glyph_rows as scanner
from . import ocr_find_unreviewed_glyph_rows_conservative as conservative
from .ocr_glyph_facit_store import canonical_store_for_facit, verify_facit
from .ocr_glyph_review_delete import load_facit_with_typography

BASELINE_FORMAT = "saol14-ocr-conservative-baseline-v1"
ROWS_FORMAT = "saol14-ocr-baseline-rows-v1"
PROBLEMS_FORMAT = "saol14-ocr-baseline-problems-v1"
SUMMARY_FORMAT = "saol14-ocr-baseline-summary-v1"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_store(store_dir: Path) -> str:
    """Hash split facit by relative path and bytes, independent of filesystem metadata."""
    digest = hashlib.sha256()
    files = sorted(path for path in Path(store_dir).rglob("*.json") if path.is_file())
    for path in files:
        relative = path.relative_to(store_dir).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _match_record(match) -> dict:
    x0 = int(getattr(match, "x", 0))
    baseline = int(getattr(match, "baseline", 0))
    pixels = sorted(
        (int(x) - x0, int(y) - baseline)
        for x, y in (getattr(match, "pixels", None) or ())
    )
    raster_payload = json.dumps(pixels, separators=(",", ":")).encode("utf-8")
    return {
        "label": str(getattr(match, "label", "")),
        "style": str(getattr(match, "style", "")),
        "x": x0,
        "baseline": baseline,
        "model_pixels": int(getattr(match, "model_pixels", len(pixels)) or 0),
        "sources": int(getattr(match, "sources", 0) or 0),
        "raster_sha256": _sha256_bytes(raster_payload),
    }


def _row_record(page: int, position: tuple[int, int], state: dict, work) -> dict:
    matches = list(state.get("matches") or state.get("selected") or [])
    matches.sort(
        key=lambda match: (
            int(getattr(match, "x", 0)),
            int(getattr(match, "baseline", 0)),
            str(getattr(match, "label", "")),
            str(getattr(match, "style", "")),
        )
    )
    crop_box = state.get("crop_box")
    if crop_box is not None:
        crop_box = [int(value) for value in crop_box]
    baseline = state.get("baseline")
    return {
        "page": int(page),
        "column": int(position[0]),
        "row": int(position[1]),
        "crop_box": crop_box,
        "baseline": None if baseline is None else int(baseline),
        "covered_pixels": int(work.covered_pixels),
        "source_pixels": int(work.source_pixels),
        "fully_exact": bool(work.fully_exact),
        "unreviewed_matches": int(work.unreviewed_matches),
        "needs_work": bool(work.needs_work),
        "text": str(state.get("text") or ""),
        "matches": [_match_record(match) for match in matches],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_rows_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def capture(args: argparse.Namespace) -> dict:
    facit = Path(args.facit)
    store = canonical_store_for_facit(facit)
    if store is None:
        raise ValueError(
            "baseline capture requires the canonical "
            "glyphs/saol14-manual-glyph-facit-v2.json path"
        )
    ok, message = verify_facit(facit, store)
    if not ok:
        raise ValueError(message)

    models = load_facit_with_typography(facit)
    if args.expect_facit_models is not None and len(models) != args.expect_facit_models:
        raise ValueError(
            f"expected {args.expect_facit_models} facit models, found {len(models)}"
        )

    rows: list[dict] = []
    original_classify = scanner.classify_row_state

    def observing_classify(page, position, state):
        work = original_classify(page, position, state)
        rows.append(_row_record(page, position, state, work))
        return work

    scanner.classify_row_state = observing_classify
    original_argv = sys.argv
    scan_argv = [
        "ocr_find_unreviewed_glyph_rows_conservative",
        str(args.jsonl),
        "--facit",
        str(facit),
        "--threshold",
        str(args.threshold),
        "--start-page",
        str(args.start_page),
        "--end-page",
        str(args.end_page),
    ]
    if args.slow_row_seconds > 0:
        scan_argv += ["--slow-row-seconds", str(args.slow_row_seconds)]
    try:
        sys.argv = scan_argv
        result = conservative.main()
    finally:
        sys.argv = original_argv
        scanner.classify_row_state = original_classify
    if result != 0:
        raise RuntimeError(f"conservative scanner returned {result}")

    rows.sort(key=lambda row: (row["page"], row["column"], row["row"]))
    problems = [row for row in rows if row["needs_work"]]
    pages = sorted({int(row["page"]) for row in rows})
    exact = sum(bool(row["fully_exact"]) for row in rows)

    output_dir = Path(args.output_dir)
    rows_path = output_dir / "rows.jsonl"
    problems_path = output_dir / "problems.json"
    summary_path = output_dir / "summary.json"
    manifest_path = output_dir / "manifest.json"

    summary = {
        "format": SUMMARY_FORMAT,
        "pages": len(pages),
        "first_page": min(pages) if pages else None,
        "last_page": max(pages) if pages else None,
        "rows": len(rows),
        "exact": exact,
        "needs_work": len(problems),
        "facit_models": len(models),
    }
    _write_rows_jsonl(rows_path, rows)
    _write_json(
        problems_path,
        {
            "format": PROBLEMS_FORMAT,
            "rows": problems,
        },
    )
    _write_json(summary_path, summary)

    manifest = {
        "format": BASELINE_FORMAT,
        "algorithm": "ocr_find_unreviewed_glyph_rows_conservative",
        "git_commit": _git_commit(),
        "parameters": {
            "threshold": int(args.threshold),
            "start_page": int(args.start_page),
            "end_page": int(args.end_page),
        },
        "source": {
            "jsonl": str(Path(args.jsonl)),
            "sha256": _sha256_file(Path(args.jsonl)),
        },
        "facit": {
            "aggregate": str(facit),
            "aggregate_sha256": _sha256_file(facit),
            "split_store": str(store),
            "split_store_sha256": _sha256_store(store),
            "models": len(models),
            "verified_equal": True,
        },
        "outputs": {
            "rows": {"path": "rows.jsonl", "sha256": _sha256_file(rows_path)},
            "problems": {"path": "problems.json", "sha256": _sha256_file(problems_path)},
            "summary": {"path": "summary.json", "sha256": _sha256_file(summary_path)},
        },
    }
    _write_json(manifest_path, manifest)
    print(
        "baseline: "
        f"pages={summary['pages']} rows={summary['rows']} "
        f"exact={summary['exact']}/{summary['rows']} "
        f"needs_work={summary['needs_work']} facit_models={summary['facit_models']}"
    )
    print(f"baseline: saved to {output_dir}")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture a permanent deterministic baseline from the conservative SAOL14 OCR scanner"
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--facit", type=Path, required=True)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=100)
    parser.add_argument("--threshold", type=int, default=210)
    parser.add_argument("--slow-row-seconds", type=float, default=0.20)
    parser.add_argument("--expect-facit-models", type=int, default=428)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/reference/saol14-ocr/conservative-v1"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    capture(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
