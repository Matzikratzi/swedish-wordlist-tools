from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

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
    args = ap.parse_args()

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
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        page_found = 0
        for position in context["positions"]:
            state = load_review_state_pixel_array(context, position, models)
            scanned_rows += 1
            work = classify_row_state(page, position, state)
            if not work.needs_work:
                continue
            print(format_row_work(work), flush=True)
            work_rows.append(work)
            page_found += 1
        print(
            f"scan: page {page}: {page_found} rows need work / {len(context['positions'])} rows",
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
