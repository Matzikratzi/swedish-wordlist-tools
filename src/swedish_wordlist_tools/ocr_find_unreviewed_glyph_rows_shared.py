from __future__ import annotations

"""Batch scanner using the same shared pixel-review loader as the queue editor."""

from time import perf_counter

from . import ocr_find_unreviewed_glyph_rows as scanner
from .ocr_priority_fast_path import priority_stats, reset_priority_stats
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


scanner.build_page_context_pixel_array = build_page_context_pixel_array
scanner.load_review_state_pixel_array = load_review_state_pixel_array


def main() -> int:
    reset_priority_stats()
    started = perf_counter()
    status = scanner.main()
    elapsed = perf_counter() - started
    stats = priority_stats()
    print(
        "benchmark: "
        f"wall={elapsed:.3f}s "
        f"fast_calls={stats['calls']} "
        f"fast_success={stats['successful_calls']} "
        f"placements={stats['placements_tested']} "
        f"page_prepares={stats.get('page_prepares', 0)} "
        f"order_builds={stats.get('order_builds', 0)} "
        f"hints=headword:{stats['headword_hints']},homonym:{stats['homonym_hints']},"
        f"continuation:{stats['continuation_hints']},unknown:{stats['unknown_hints']}",
        flush=True,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
