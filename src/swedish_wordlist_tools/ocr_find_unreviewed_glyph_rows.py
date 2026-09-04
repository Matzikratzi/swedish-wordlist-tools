from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from .ocr_glyph_review_delete import _match_reviewed, load_facit_with_typography
from .ocr_prepare_sequential_page import _page_from_row, read_jsonl
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


QUEUE_FORMAT = "saol14-glyph-review-row-queue-v1"


@dataclass(frozen=True)
class RowWork:
    page: int
    column: int
    row: int
    unreviewed_matches: int
    covered_pixels: int
    source_pixels: int
    fully_exact: bool

    @property
    def needs_work(self) -> bool:
        return self.unreviewed_matches > 0 or not self.fully_exact


def classify_row_state(page: int, position: tuple[int, int], state: dict) -> RowWork:
    """Classify one analysed row without changing facit or review state."""
    matches = state.get("matches") or []
    return RowWork(
        page=int(page),
        column=int(position[0]),
        row=int(position[1]),
        unreviewed_matches=sum(not _match_reviewed(match) for match in matches),
        covered_pixels=int(state.get("covered_pixels") or 0),
        source_pixels=int(state.get("source_pixels") or 0),
        fully_exact=bool(state.get("fully_exact", False)),
    )


def format_row_work(work: RowWork) -> str:
    pixel_status = "exact" if work.fully_exact else f"{work.covered_pixels}/{work.source_pixels}"
    return (
        f"page {work.page} column {work.column} row {work.row}: "
        f"unreviewed={work.unreviewed_matches} pixels={pixel_status}"
    )


def format_slow_row(page: int, position: tuple[int, int], elapsed: float) -> str:
    column, row = position
    return f"slow-row: page {page} column {column} row {row}: {elapsed:.3f} s"


def write_review_queue(path: Path, rows: list[RowWork]) -> None:
    payload = {
        "format": QUEUE_FORMAT,
        "rows": [asdict(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _available_pages(jsonl: Path) -> list[int]:
    pages = {
        page
        for row in read_jsonl(jsonl)
        if (page := _page_from_row(row)) is not None
    }
    return sorted(pages)


def _selected_pages(
    available: list[int],
    *,
    pages: list[int] | None,
    start_page: int | None,
    end_page: int | None,
) -> list[int]:
    selected = list(available)
    if pages:
        wanted = set(pages)
        selected = [page for page in selected if page in wanted]
        missing = sorted(wanted - set(selected))
        if missing:
            raise ValueError(f"pages are not present in JSONL: {missing}")
    if start_page is not None:
        selected = [page for page in selected if page >= start_page]
    if end_page is not None:
        selected = [page for page in selected if page <= end_page]
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "List OCR rows that contain unreviewed facit matches or are not pixel-exact. "
            "The facit is only read; it is never modified."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--page",
        type=int,
        action="append",
        dest="pages",
        help="scan only this page; may be supplied more than once",
    )
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--output",
        type=Path,
        help="save all reported rows as a JSON review queue",
    )
    ap.add_argument(
        "--progress",
        action="store_true",
        help="print every row before and after glyph analysis, including elapsed time",
    )
    ap.add_argument(
        "--slow-row-seconds",
        type=float,
        default=0.5,
        help="report rows whose glyph analysis takes at least this many seconds; 0 disables (default: 0.5)",
    )
    args = ap.parse_args()
    if args.slow_row_seconds < 0:
        raise ValueError("--slow-row-seconds must be >= 0")

    available = _available_pages(args.jsonl)
    pages = _selected_pages(
        available,
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    work_rows: list[RowWork] = []
    scanned_rows = 0
    for page in pages:
        page_prepare_started = perf_counter()
        print(f"scan: page {page}: förbereder sida ...", flush=True)
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        prepare_elapsed = perf_counter() - page_prepare_started
        # The scanner only needs periodic progress plus rows that require human
        # attention. Successful automatic ownership repairs are implementation
        # detail; true ownership conflicts remain visible as FEL diagnostics.
        context["quiet_successful_ownership"] = not args.progress
        positions = context["positions"]
        print(
            f"scan: page {page}: förberedelse klar på {prepare_elapsed:.1f} s; "
            f"börjar glyphanalys av {len(positions)} rader",
            flush=True,
        )
        page_found = 0
        page_scan_started = perf_counter()
        for index, position in enumerate(positions, start=1):
            column, row = position
            if args.progress:
                print(
                    f"scan: page {page}: [{index}] analyserar c{column} r{row} ...",
                    flush=True,
                )
            row_started = perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            row_elapsed = perf_counter() - row_started
            if args.progress:
                print(
                    f"scan: page {page}: [{index}] c{column} r{row} klar på {row_elapsed:.3f} s",
                    flush=True,
                )
            else:
                if args.slow_row_seconds > 0 and row_elapsed >= args.slow_row_seconds:
                    print(format_slow_row(page, position, row_elapsed), flush=True)
                if index % 10 == 0:
                    elapsed = perf_counter() - page_scan_started
                    print(
                        f"scan: page {page}: {index} rader analyserade, senast c{column} r{row} "
                        f"({elapsed:.1f} s)",
                        flush=True,
                    )
            scanned_rows += 1
            work = classify_row_state(page, position, state)
            if not work.needs_work:
                continue
            print(format_row_work(work), flush=True)
            work_rows.append(work)
            page_found += 1
        page_scan_elapsed = perf_counter() - page_scan_started
        print(
            f"scan: page {page}: {page_found} rows need work / {len(positions)} rows "
            f"(glyphanalys {page_scan_elapsed:.3f} s)",
            flush=True,
        )

    if args.output is not None:
        write_review_queue(args.output, work_rows)
        print(f"scan: saved {len(work_rows)} rows to {args.output}", flush=True)

    print(
        f"scan: {len(work_rows)} rows need work / {scanned_rows} scanned rows on {len(pages)} pages",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
