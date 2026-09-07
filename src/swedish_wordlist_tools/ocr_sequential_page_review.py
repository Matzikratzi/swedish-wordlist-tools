from __future__ import annotations

import argparse
import base64
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
UNKNOWN_ROLE = "unknown"
DEFAULT_FACIT_V2 = Path("glyphs/saol14-manual-glyph-facit-v2.json")
CONTEXT_COLUMNS = 3
CONTEXT_ROWS = 4
CONTEXT_OVERLAP_FRACTION = 0.08


def _safe_load_source_image(source: str) -> Image.Image | None:
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
    row["five_row_context"] = debug.get("five_row_context")
    row["target_word_bbox_in_crop"] = debug.get("target_word_bbox_in_crop")
    tesseract = debug.get("tesseract")
    if isinstance(tesseract, dict):
        row["target_page_word_bbox"] = tesseract.get("raw_bbox")
    return row


def _debug_has_jsonl_anchor(path: Path) -> bool:
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


def _segment_index_for_bbox(
    bbox: list[int] | tuple[int, int, int, int] | None,
    page_width: int,
    page_height: int,
) -> tuple[int, int] | None:
    if not bbox or len(bbox) != 4:
        return None
    try:
        left, top, width, height = (int(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    cx = left + width / 2
    cy = top + height / 2
    column = max(0, min(CONTEXT_COLUMNS - 1, int(CONTEXT_COLUMNS * cx / max(1, page_width))))
    band = max(0, min(CONTEXT_ROWS - 1, int(CONTEXT_ROWS * cy / max(1, page_height))))
    return column, band


def _segment_box(
    column: int,
    band: int,
    page_width: int,
    page_height: int,
    *,
    overlap_fraction: float = CONTEXT_OVERLAP_FRACTION,
) -> tuple[int, int, int, int]:
    core_x0 = (column * page_width) // CONTEXT_COLUMNS
    core_x1 = ((column + 1) * page_width) // CONTEXT_COLUMNS
    core_y0 = (band * page_height) // CONTEXT_ROWS
    core_y1 = ((band + 1) * page_height) // CONTEXT_ROWS
    pad_x = round((core_x1 - core_x0) * overlap_fraction)
    pad_y = round((core_y1 - core_y0) * overlap_fraction)
    return (
        max(0, core_x0 - pad_x),
        max(0, core_y0 - pad_y),
        min(page_width, core_x1 + pad_x),
        min(page_height, core_y1 + pad_y),
    )


def _png_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _write_page_context_segments(
    rows: list[dict],
    page_image: Image.Image,
    out_dir: Path,
) -> int:
    """Write 3 x 4 overlapping facsimile segments and link each OCR row to one.

    The PNG files are retained for inspection, but each row receives an embedded
    data URI so the generated review HTML remains self-contained.  This avoids
    broken relative image links when desktop browsers open the HTML through a
    document portal such as /run/user/.../doc/....
    """
    context_dir = out_dir / "context"
    context_dir.mkdir(exist_ok=True)
    segments: dict[
        tuple[int, int],
        tuple[str, str, tuple[int, int, int, int]],
    ] = {}

    for band in range(CONTEXT_ROWS):
        for column in range(CONTEXT_COLUMNS):
            box = _segment_box(column, band, page_image.width, page_image.height)
            filename = f"page-segment-c{column + 1}-r{band + 1}.png"
            image_path = context_dir / filename
            page_image.crop(box).save(image_path)
            segments[(column, band)] = (
                _png_data_uri(image_path),
                f"context/{filename}",
                box,
            )

    for row in rows:
        index = _segment_index_for_bbox(
            row.get("target_page_word_bbox"),
            page_image.width,
            page_image.height,
        )
        if index is None:
            index = _segment_index_for_bbox(
                row.get("page_word_bbox"),
                page_image.width,
                page_image.height,
            )
        if index is None:
            continue
        image_data, image_file, box = segments[index]
        row["context_image"] = image_data
        row["context_image_file"] = image_file
        row["context_image_bbox"] = list(box)
        row["context_segment"] = [index[0] + 1, index[1] + 1]

    return len(segments)


def _ordered_exact(row: dict) -> list[dict]:
    return sorted(
        [m for m in row.get("exact") or [] if str(m.get("label") or "")],
        key=lambda m: (int(m.get("x") or 0), str(m.get("label") or "")),
    )


def _style_runs(row: dict) -> list[dict]:
    """Collapse verified semantic typography-role matches into adjacent runs.

    Facit-v2 models migrated from the old bold/roman/italic facit have role
    ``unknown``. They remain valid exact raster evidence for OCR geometry, but
    are deliberately omitted here so they cannot masquerade as semantic
    typography evidence.
    """
    runs: list[dict] = []
    for match in _ordered_exact(row):
        role = str(match.get("style") or UNKNOWN_ROLE)
        if role == UNKNOWN_ROLE:
            continue
        label = str(match.get("label") or "")
        if runs and runs[-1]["style"] == role:
            runs[-1]["text"] += label
            runs[-1]["glyphs"] += 1
        else:
            runs.append({"style": role, "text": label, "glyphs": 1})
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
    ap.add_argument("--facit", type=Path, default=DEFAULT_FACIT_V2)
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
    if not args.facit.is_file():
        raise SystemExit(
            f"facit not found: {args.facit}; create v2 first with "
            "python -m swedish_wordlist_tools.ocr_migrate_glyph_facit_v2"
        )

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

    print("[context] writing 12 overlapping facsimile page segments...", flush=True)
    page_image = _safe_load_source_image(str(report.get("source") or ""))
    context_images = 0
    if page_image is not None:
        context_images = _write_page_context_segments(analysed, page_image, args.out_dir)

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
    print(f"facit={args.facit}")
    print(f"jsonl_rows={report.get('jsonl_rows', 0)}")
    print(f"jsonl_reference_tokens={report.get('jsonl_reference_tokens', 0)}")
    print(f"ocr_words={len(debug_files)}")
    print(f"hinted_words={report.get('hinted_words', 0)}")
    print(f"five_row_context_words={report.get('five_row_context_words', 0)}")
    print(f"five_row_review_words={five_row_used}")
    print(f"review_words={len(analysed)}")
    print(f"excluded_unanchored_words={excluded_unanchored}")
    print(f"analysis_workers={args.workers}")
    print(f"context_images={context_images}")
    print(f"fully_exact={exact}")
    print(f"incomplete_words={incomplete}")
    print(f"unknown_occurrences={occurrences}")
    print(f"unique_unknown_rasters={len(candidates)}")
    print(f"candidates_with_jsonl_suggestion={suggested}")
    print(f"semantic_multi_role_words={len(multi_style_rows)}")
    print(f"semantic_role_sequences={len(sequence_counts)}")
    print(f"semantic_role_transitions={sum(transition_counts.values())}")

    if sequence_counts:
        print("\nSEMANTIC TYPOGRAPHY ROLE SEQUENCES:")
        for sequence, count in sequence_counts.most_common():
            print(f"  {count:4d}  {' -> '.join(sequence)}")

    if transition_counts:
        print("\nSEMANTIC TYPOGRAPHY ROLE TRANSITIONS:")
        for (left, right), count in transition_counts.most_common():
            print(f"  {count:4d}  {left} -> {right}")

    if multi_style_rows:
        print("\nMULTI-ROLE EXAMPLES:")
        for row in multi_style_rows[:30]:
            print(f"  {_row_name(row)!r}: {_format_style_runs(row)}")

    print(f"review_html={review_html}")
    print(f"facit_html={facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
