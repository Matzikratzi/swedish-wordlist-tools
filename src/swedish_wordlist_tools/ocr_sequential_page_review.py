from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from . import ocr_exact_glyph_review_queue_v12 as review_v12
from . import ocr_prepare_sequential_page as sequential_page
from .ocr_editable_unknown_glyph_review import build_html as build_editable_unknown_html
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import load_facit
from .ocr_unique_unknown_glyph_review import collect_candidates

_WORKER_MODELS = None


def _safe_load_source_image(source: str) -> Image.Image | None:
    """Load a local page image or URL without treating an empty path as '.'."""
    if not source:
        return None
    local = Path(source)
    if local.is_file():
        return Image.open(local).convert("L")
    try:
        with urllib.request.urlopen(source, timeout=30) as response, NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(response.read())
            tmp.flush()
            return Image.open(tmp.name).convert("L")
    except Exception:
        return None


def _analyse_with_debug_metadata(path: Path, models):
    row = review_v12._analyse_one(path, models)
    debug = json.loads(path.read_text(encoding="utf-8"))
    row["jsonl_hint"] = debug.get("jsonl_hint")
    row["page_word_bbox"] = debug.get("page_word_bbox")
    row["page_source"] = debug.get("page_source")
    return row


def _debug_has_jsonl_anchor(path: Path) -> bool:
    """Cheaply reject OCR boxes that will not participate in review.

    Exact glyph matching is by far the expensive step. Page preparation already
    wrote the JSONL alignment hint into every debug file, so inspect that first
    and never raster-match unanchored page headers, page numbers, etc.
    """
    debug = json.loads(path.read_text(encoding="utf-8"))
    hint = debug.get("jsonl_hint")
    return isinstance(hint, dict) and bool(str(hint.get("text") or "").strip())


def _is_jsonl_anchored(row: dict) -> bool:
    hint = row.get("jsonl_hint")
    return isinstance(hint, dict) and bool(str(hint.get("text") or "").strip())


def _init_analysis_worker(facit_path: str) -> None:
    global _WORKER_MODELS
    _WORKER_MODELS = load_facit(Path(facit_path))


def _analyse_path_worker(path_text: str) -> dict:
    if _WORKER_MODELS is None:
        raise RuntimeError("OCR analysis worker was not initialized")
    return _analyse_with_debug_metadata(Path(path_text), _WORKER_MODELS)


def _default_workers() -> int:
    return max(1, min(8, os.cpu_count() or 1))


def _print_progress(done: int, total: int, workers: int, *, force: bool = False) -> None:
    if total <= 0:
        return
    percent = (100 * done) // total
    # Keep output useful rather than printing one line per word. Always show
    # start/end and approximately every five percentage points.
    previous = (100 * max(0, done - 1)) // total
    if force or done == 0 or done == total or percent // 5 > previous // 5:
        print(f"[analyse] {done}/{total} ({percent}%) workers={workers}", flush=True)


def _analyse_paths(paths: list[Path], facit_path: Path, workers: int) -> list[dict]:
    if not paths:
        return []
    workers = max(1, workers)
    _print_progress(0, len(paths), workers, force=True)

    if workers == 1:
        models = load_facit(facit_path)
        rows = []
        for done, path in enumerate(paths, 1):
            rows.append(_analyse_with_debug_metadata(path, models))
            _print_progress(done, len(paths), workers)
        return rows

    rows: list[dict | None] = [None] * len(paths)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_analysis_worker,
        initargs=(str(facit_path),),
    ) as executor:
        futures = {
            executor.submit(_analyse_path_worker, str(path)): index
            for index, path in enumerate(paths)
        }
        for done, future in enumerate(as_completed(futures), 1):
            rows[futures[future]] = future.result()
            _print_progress(done, len(paths), workers)

    return [row for row in rows if row is not None]


def _ordered_exact(row: dict) -> list[dict]:
    return sorted(
        [m for m in row.get("exact") or [] if str(m.get("label") or "")],
        key=lambda m: (int(m.get("x") or 0), str(m.get("label") or "")),
    )


def _style_runs(row: dict) -> list[dict]:
    """Collapse exact glyphs into adjacent typography runs."""
    runs: list[dict] = []
    for match in _ordered_exact(row):
        style = str(match.get("style") or "roman")
        label = str(match.get("label") or "")
        if runs and runs[-1]["style"] == style:
            runs[-1]["text"] += label
            runs[-1]["glyphs"] += 1
        else:
            runs.append({"style": style, "text": label, "glyphs": 1})
    return runs


def _style_sequence(row: dict) -> tuple[str, ...]:
    return tuple(run["style"] for run in _style_runs(row))


def _style_sequence_counts(rows: list[dict]) -> Counter[tuple[str, ...]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        sequence = _style_sequence(row)
        if sequence:
            counts[sequence] += 1
    return counts


def _style_transition_counts(rows: list[dict]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        sequence = _style_sequence(row)
        for left, right in zip(sequence, sequence[1:]):
            counts[(left, right)] += 1
    return counts


def _row_name(row: dict) -> str:
    hint = row.get("jsonl_hint")
    if isinstance(hint, dict):
        for key in ("ord", "text", "token"):
            value = str(hint.get(key) or "").strip()
            if value:
                return value
    return str(row.get("word") or row.get("expected") or "?")


def _format_style_runs(row: dict) -> str:
    return " | ".join(f"{run['style']}:{run['text']}" for run in _style_runs(row))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Read one SAOL facsimile page in sequence, accept exact known glyphs, "
            "and edit only unexplained rasters anchored to JSONL dictionary text."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--review-html", type=Path)
    ap.add_argument("--facit-html", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--pad-x", type=int, default=1)
    ap.add_argument("--pad-y", type=int, default=5)
    ap.add_argument("--min-confidence", type=float, default=-1.0)
    ap.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="parallel glyph-analysis processes (default: min(8, CPU count); use 1 for serial)",
    )
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("--workers must be at least 1")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    review_html = args.review_html or (args.out_dir / "unknown-glyph-review.html")
    facit_html = args.facit_html or (args.out_dir / "glyph-facit-table.html")

    print(f"[prepare] page {args.page}: Tesseract, JSONL alignment and five-row crops...", flush=True)
    sequential_page._load_source_image = _safe_load_source_image
    report = sequential_page.prepare_page(
        args.jsonl,
        args.page,
        args.out_dir,
        threshold=args.threshold,
        lang=args.lang,
        psm=args.psm,
        pad_x=args.pad_x,
        pad_y=args.pad_y,
        min_confidence=args.min_confidence,
    )

    debug_files = sorted(args.out_dir.glob("saol14-word-debug-*.json"))
    if not debug_files:
        raise SystemExit("page preparation produced no word-debug files")

    print(f"[prepare] complete: {len(debug_files)} OCR boxes", flush=True)
    anchored_paths = [path for path in debug_files if _debug_has_jsonl_anchor(path)]
    excluded_unanchored = len(debug_files) - len(anchored_paths)
    print(
        f"[filter] {len(anchored_paths)} JSONL-anchored boxes to analyse; "
        f"skipping {excluded_unanchored} unanchored boxes",
        flush=True,
    )

    analysed = _analyse_paths(anchored_paths, args.facit, args.workers)

    exact = sum(1 for row in analysed if row.get("fully_exact"))
    incomplete = len(analysed) - exact
    candidates = collect_candidates(analysed)
    occurrences = sum(int(c.get("occurrences") or 0) for c in candidates)
    suggested = sum(1 for c in candidates if c.get("suggestion"))
    five_row_used = sum(1 for row in analysed if row.get("five_row_context_used"))
    sequence_counts = _style_sequence_counts(analysed)
    transition_counts = _style_transition_counts(analysed)
    multi_style_rows = [row for row in analysed if len(_style_sequence(row)) > 1]

    print("[output] building review HTML...", flush=True)
    review_html.write_text(build_editable_unknown_html(analysed, args.facit), encoding="utf-8")
    facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")

    print(f"page={args.page}")
    print(f"source={report['source']}")
    print(f"jsonl_rows={report.get('jsonl_rows', 0)}")
    print(f"jsonl_reference_tokens={report.get('jsonl_reference_tokens', 0)}")
    print(f"ocr_words={len(debug_files)}")
    print(f"hinted_words={report.get('hinted_words', 0)}")
    print(f"five_row_context_words={report.get('five_row_context_words', 0)}")
    print(f"five_row_review_words={five_row_used}")
    print(f"review_words={len(analysed)}")
    print(f"excluded_unanchored_words={excluded_unanchored}")
    print(f"analysis_workers={args.workers}")
    print(f"fully_exact={exact}")
    print(f"incomplete_words={incomplete}")
    print(f"unknown_occurrences={occurrences}")
    print(f"unique_unknown_rasters={len(candidates)}")
    print(f"candidates_with_jsonl_suggestion={suggested}")
    print(f"multi_style_words={len(multi_style_rows)}")
    print(f"style_sequences={len(sequence_counts)}")
    print(f"style_transitions={sum(transition_counts.values())}")

    if sequence_counts:
        print("\nTYPOGRAPHY SEQUENCES:")
        for sequence, count in sequence_counts.most_common():
            print(f"  {count:4d}  {' -> '.join(sequence)}")

    if transition_counts:
        print("\nTYPOGRAPHY TRANSITIONS:")
        for (left, right), count in transition_counts.most_common():
            print(f"  {count:4d}  {left} -> {right}")

    if multi_style_rows:
        print("\nMULTI-STYLE EXAMPLES:")
        for row in multi_style_rows[:30]:
            print(f"  {_row_name(row)!r}: {_format_style_runs(row)}")

    print(f"review_html={review_html}")
    print(f"facit_html={facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
