from __future__ import annotations

"""Run the headword-sequence benchmark and save reference mismatches as a row-review queue.

This is diagnostic only. OCR behaviour and the benchmark exit status are
unchanged. The wrapper records rows reported by the existing reference
comparison, but omits stale crop/reference differences when the current OCR is
fully exact and produces the same text as the reference.

The wrapper is intentionally quiet by default so larger page ranges remain
readable. Pass ``--verbose`` to expose the underlying benchmark's normal stdout
diagnostics.
"""

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

from . import ocr_headword_first_glyph_sequence_benchmark as benchmark
from . import ocr_split_facit_benchmark as split_benchmark
from .ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT, RowWork


_PAGE_RE = re.compile(r"page-(\d+)$")


def _row_work(page: int, key: tuple[int, int], expected, observed) -> RowWork:
    source_pixels = 0
    covered_pixels = 0
    fully_exact = False
    if observed is not None:
        source_pixels = int(observed.get("source_pixels") or 0)
        covered_pixels = int(observed.get("covered_pixels") or 0)
        fully_exact = bool(observed.get("exact", False))
    elif expected is not None:
        source_pixels = int(expected.get("source_pixels") or 0)

    return RowWork(
        page=int(page),
        column=int(key[0]),
        row=int(key[1]),
        unreviewed_matches=0,
        covered_pixels=covered_pixels,
        source_pixels=source_pixels,
        fully_exact=fully_exact,
    )


def _snapshot(row) -> dict | None:
    if row is None:
        return None
    return {
        "text": str(row.get("text") or ""),
        "source_pixels": int(row.get("source_pixels") or 0),
        "covered_pixels": int(row.get("covered_pixels") or 0),
        "exact": bool(row.get("exact", False)),
    }


def _resolved_exact_reference_crop(expected, observed) -> bool:
    """True when a mismatch is only stale reference/crop accounting.

    We learned that the old review compaction could discard already matched
    left-edge pixels (notably homonym superscripts) and then recompute the pixel
    totals. If the current benchmark sees exactly the same text and every current
    source pixel is covered exactly, that row no longer needs manual glyph review
    even when its pixel count differs from the frozen reference.
    """
    if expected is None or observed is None:
        return False
    if str(expected.get("text") or "") != str(observed.get("text") or ""):
        return False
    if not bool(observed.get("exact", False)):
        return False
    source_pixels = int(observed.get("source_pixels") or 0)
    covered_pixels = int(observed.get("covered_pixels") or 0)
    return source_pixels > 0 and covered_pixels == source_pixels


def _queue_row(page: int, key: tuple[int, int], why: str, expected, observed) -> dict:
    work = _row_work(page, key, expected, observed)
    return {
        "page": work.page,
        "column": work.column,
        "row": work.row,
        "unreviewed_matches": work.unreviewed_matches,
        "covered_pixels": work.covered_pixels,
        "source_pixels": work.source_pixels,
        "fully_exact": work.fully_exact,
        "benchmark_mismatch": {
            "why": str(why),
            "reference": _snapshot(expected),
            "observed": _snapshot(observed),
        },
    }


def _write_queue(path: Path, rows: list[dict]) -> None:
    payload = {"format": QUEUE_FORMAT, "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--review-queue", type=Path, required=True)
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="show the underlying benchmark's normal stdout diagnostics",
    )
    queue_args, benchmark_argv = ap.parse_known_args()

    original_argv = sys.argv
    original_load_reference = split_benchmark._load_reference
    original_compare_page = split_benchmark._compare_page
    current_page: list[int | None] = [None]
    queued: dict[tuple[int, int, int], dict] = {}
    ignored_exact_crop_mismatches = 0

    def load_reference_with_page(path: Path):
        match = _PAGE_RE.fullmatch(Path(path).stem)
        current_page[0] = int(match.group(1)) if match else None
        return original_load_reference(path)

    def compare_and_collect(reference, actual):
        nonlocal ignored_exact_crop_mismatches
        mismatches = original_compare_page(reference, actual)
        page = current_page[0]
        if page is None and mismatches:
            raise RuntimeError("could not determine page number while writing review queue")
        for key, why, expected, observed in mismatches:
            if _resolved_exact_reference_crop(expected, observed):
                ignored_exact_crop_mismatches += 1
                continue
            row = _queue_row(int(page), key, why, expected, observed)
            queued[(row["page"], row["column"], row["row"])] = row
        return mismatches

    split_benchmark._load_reference = load_reference_with_page
    split_benchmark._compare_page = compare_and_collect
    sys.argv = [original_argv[0], *benchmark_argv]
    try:
        if queue_args.verbose:
            result = benchmark.main()
        else:
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                with contextlib.redirect_stdout(devnull):
                    result = benchmark.main()
    finally:
        sys.argv = original_argv
        split_benchmark._load_reference = original_load_reference
        split_benchmark._compare_page = original_compare_page

    rows = [queued[key] for key in sorted(queued)]
    _write_queue(queue_args.review_queue, rows)
    pages = sorted({row["page"] for row in rows})
    page_summary = f" pages={pages[0]}..{pages[-1]}" if pages else ""
    print(
        f"review-queue: saved {len(rows)} benchmark mismatch rows{page_summary} "
        f"to {queue_args.review_queue}; ignored {ignored_exact_crop_mismatches} "
        "resolved exact reference/crop mismatches",
        flush=True,
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
