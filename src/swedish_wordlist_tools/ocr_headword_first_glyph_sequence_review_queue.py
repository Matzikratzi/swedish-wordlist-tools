from __future__ import annotations

"""Run the ordinary scanner/reference benchmark and save every mismatch as a queue.

Despite the historical module name, this wrapper no longer runs the old
benchmark experiment stack.  OCR behaviour is exactly the ordinary scanner
path; the wrapper only collects frozen-reference mismatches into the existing
review-queue format.
"""

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

from . import ocr_scanner_reference_benchmark as benchmark
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
        help="show the underlying scanner/reference comparison diagnostics",
    )
    queue_args, benchmark_argv = ap.parse_known_args()

    original_argv = sys.argv
    original_load_reference = benchmark._load_reference
    original_compare_page = benchmark._compare_page
    current_page: list[int | None] = [None]
    queued: dict[tuple[int, int, int], dict] = {}

    def load_reference_with_page(path: Path):
        match = _PAGE_RE.fullmatch(Path(path).stem)
        current_page[0] = int(match.group(1)) if match else None
        return original_load_reference(path)

    def compare_and_collect(reference, actual):
        mismatches = original_compare_page(reference, actual)
        page = current_page[0]
        if page is None and mismatches:
            raise RuntimeError("could not determine page number while writing review queue")
        for key, why, expected, observed in mismatches:
            row = _queue_row(int(page), key, why, expected, observed)
            queued[(row["page"], row["column"], row["row"])] = row
        return mismatches

    benchmark._load_reference = load_reference_with_page
    benchmark._compare_page = compare_and_collect
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
        benchmark._load_reference = original_load_reference
        benchmark._compare_page = original_compare_page

    rows = [queued[key] for key in sorted(queued)]
    _write_queue(queue_args.review_queue, rows)
    pages = sorted({row["page"] for row in rows})
    page_summary = f" pages={pages[0]}..{pages[-1]}" if pages else ""
    print(
        f"review-queue: saved {len(rows)} scanner/reference mismatch rows{page_summary} "
        f"to {queue_args.review_queue}",
        flush=True,
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
