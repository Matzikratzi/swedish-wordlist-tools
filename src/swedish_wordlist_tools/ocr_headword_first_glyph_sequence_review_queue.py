from __future__ import annotations

"""Run the headword-sequence benchmark and save reference mismatches as a row-review queue.

This is diagnostic only.  OCR behaviour and the benchmark exit status are
unchanged; the wrapper merely records the rows already reported by the existing
reference comparison.
"""

import argparse
import re
import sys
from pathlib import Path

from . import ocr_headword_first_glyph_sequence_benchmark as benchmark
from . import ocr_split_facit_benchmark as split_benchmark
from .ocr_find_unreviewed_glyph_rows import RowWork, write_review_queue


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


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--review-queue", type=Path, required=True)
    queue_args, benchmark_argv = ap.parse_known_args()

    original_argv = sys.argv
    original_load_reference = split_benchmark._load_reference
    original_compare_page = split_benchmark._compare_page
    current_page: list[int | None] = [None]
    queued: dict[tuple[int, int, int], RowWork] = {}

    def load_reference_with_page(path: Path):
        match = _PAGE_RE.fullmatch(Path(path).stem)
        current_page[0] = int(match.group(1)) if match else None
        return original_load_reference(path)

    def compare_and_collect(reference, actual):
        mismatches = original_compare_page(reference, actual)
        page = current_page[0]
        if page is None and mismatches:
            raise RuntimeError("could not determine page number while writing review queue")
        for key, _why, expected, observed in mismatches:
            work = _row_work(int(page), key, expected, observed)
            queued[(work.page, work.column, work.row)] = work
        return mismatches

    split_benchmark._load_reference = load_reference_with_page
    split_benchmark._compare_page = compare_and_collect
    sys.argv = [original_argv[0], *benchmark_argv]
    try:
        result = benchmark.main()
    finally:
        sys.argv = original_argv
        split_benchmark._load_reference = original_load_reference
        split_benchmark._compare_page = original_compare_page

    rows = [queued[key] for key in sorted(queued)]
    write_review_queue(queue_args.review_queue, rows)
    print(
        f"review-queue: saved {len(rows)} benchmark mismatch rows to {queue_args.review_queue}",
        flush=True,
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
