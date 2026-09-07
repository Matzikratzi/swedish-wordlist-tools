from __future__ import annotations

import argparse
import contextlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from .ocr_glyph_review_delete import _match_reviewed, load_facit_with_typography
from .ocr_prepare_sequential_page import _page_from_row, read_jsonl
from .ocr_priority_fast_path import priority_stats
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


def _stat_delta(before: dict[str, int], after: dict[str, int], key: str) -> int:
    return int(after.get(key, 0)) - int(before.get(key, 0))


def _format_stage_timings(state: dict) -> str:
    timings = state.get("shared_stage_timings") or {}
    if not timings:
        return ""
    return " stages=" + ",".join(
        f"{name}:{float(value):.3f}s" for name, value in timings.items()
    )


def _format_state_text(state: dict) -> str:
    text = str(state.get("text") or "").replace("\n", " ").strip()
    return f" text={text!r}" if text else ""


def _short_text(text: str, width: int = 110) -> str:
    text = " ".join(str(text).split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def format_timed_row(
    prefix: str,
    page: int,
    position: tuple[int, int],
    elapsed: float,
    state: dict,
    *,
    stats_before: dict[str, int] | None = None,
    stats_after: dict[str, int] | None = None,
) -> str:
    column, row = position
    text = f"{prefix}: page {page} column {column} row {row}: {elapsed:.3f} s"
    if stats_before is not None and stats_after is not None:
        calls = _stat_delta(stats_before, stats_after, "calls")
        success = _stat_delta(stats_before, stats_after, "successful_calls")
        placements = _stat_delta(stats_before, stats_after, "placements_tested")
        segmented = _stat_delta(stats_before, stats_after, "segmented_success")
        probes = _stat_delta(stats_before, stats_after, "segmented_probes")
        parts = _stat_delta(stats_before, stats_after, "segmented_parts")
        text += f" fast_calls={calls} fast_success={success} placements={placements}"
        if probes or segmented:
            text += f" split={segmented}/{probes} parts={parts}"
    return text + _format_stage_timings(state) + _format_state_text(state)


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


def _quiet_call_preserving_warnings(function, *args, **kwargs):
    """Run scanner internals quietly, replaying only warning lines."""
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            return function(*args, **kwargs)
    finally:
        for line in captured.getvalue().splitlines():
            if "VARNING" in line:
                print(line, flush=True)


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
        help="print detailed scanner/page diagnostics and every row",
    )
    ap.add_argument(
        "--slow-row-seconds",
        type=float,
        default=0.0,
        help="also report rows immediately when glyph analysis takes at least this many seconds; 0 disables",
    )
    ap.add_argument(
        "--sample-every",
        type=int,
        default=0,
        help="also report every Nth non-slow row; 0 disables",
    )
    args = ap.parse_args()
    if args.slow_row_seconds < 0:
        raise ValueError("--slow-row-seconds must be >= 0")
    if args.sample_every < 0:
        raise ValueError("--sample-every must be >= 0")

    available = _available_pages(args.jsonl)
    pages = _selected_pages(
        available,
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    scan_started = perf_counter()
    models = load_facit_with_typography(args.facit)
    work_rows: list[RowWork] = []
    scanned_rows = 0
    exact_rows = 0
    timings: list[tuple[float, int, int, int, str]] = []

    for page in pages:
        if args.progress:
            print(f"scan: page {page}: förbereder sida ...", flush=True)
            context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        else:
            context = _quiet_call_preserving_warnings(
                build_page_context_pixel_array,
                args.jsonl,
                page,
                args.threshold,
            )
        context["quiet_successful_ownership"] = not args.progress
        positions = context["positions"]

        if args.progress:
            print(
                f"scan: page {page}: börjar glyphanalys av {len(positions)} rader",
                flush=True,
            )

        current_column: int | None = None
        column_started = perf_counter()
        column_rows = 0
        column_exact = 0
        column_work = 0

        def finish_column(column: int | None) -> None:
            nonlocal column_started, column_rows, column_exact, column_work
            if column is None:
                return
            elapsed = perf_counter() - column_started
            print(
                f"page={page} column={column} rows={column_rows} "
                f"exact={column_exact}/{column_rows} needs_work={column_work} "
                f"time={elapsed:.3f}s",
                flush=True,
            )

        for index, position in enumerate(positions, start=1):
            column, row = map(int, position)
            if current_column is None:
                current_column = column
                column_started = perf_counter()
                column_rows = column_exact = column_work = 0
            elif column != current_column:
                finish_column(current_column)
                current_column = column
                column_started = perf_counter()
                column_rows = column_exact = column_work = 0

            if args.progress:
                print(
                    f"scan: page {page}: [{index}] analyserar c{column} r{row} ...",
                    flush=True,
                )

            stats_before = priority_stats()
            row_started = perf_counter()
            if args.progress:
                state = load_review_state_pixel_array(context, position, models)
            else:
                state = _quiet_call_preserving_warnings(
                    load_review_state_pixel_array,
                    context,
                    position,
                    models,
                )
            row_elapsed = perf_counter() - row_started
            stats_after = priority_stats()

            timings.append(
                (row_elapsed, page, column, row, str(state.get("text") or ""))
            )
            scanned_rows += 1
            column_rows += 1

            work = classify_row_state(page, position, state)
            if work.fully_exact:
                exact_rows += 1
                column_exact += 1

            if work.needs_work:
                print(format_row_work(work), flush=True)
                work_rows.append(work)
                column_work += 1

            if args.progress:
                print(
                    f"scan: page {page}: [{index}] c{column} r{row} klar på {row_elapsed:.3f} s",
                    flush=True,
                )
            else:
                is_slow = args.slow_row_seconds > 0 and row_elapsed >= args.slow_row_seconds
                is_sample = args.sample_every > 0 and index % args.sample_every == 0 and not is_slow
                if is_slow:
                    print(
                        format_timed_row(
                            "slow-row",
                            page,
                            position,
                            row_elapsed,
                            state,
                            stats_before=stats_before,
                            stats_after=stats_after,
                        ),
                        flush=True,
                    )
                elif is_sample:
                    print(
                        format_timed_row(
                            "sample-row",
                            page,
                            position,
                            row_elapsed,
                            state,
                            stats_before=stats_before,
                            stats_after=stats_after,
                        ),
                        flush=True,
                    )

        finish_column(current_column)

    if args.output is not None:
        write_review_queue(args.output, work_rows)
        print(f"scan: saved {len(work_rows)} rows to {args.output}", flush=True)

    total_wall = perf_counter() - scan_started
    row_time = sum(item[0] for item in timings)
    average_row = row_time / len(timings) if timings else 0.0
    print(
        f"summary: pages={len(pages)} rows={scanned_rows} exact={exact_rows}/{scanned_rows} "
        f"needs_work={len(work_rows)} total_time={total_wall:.3f}s "
        f"average_row_time={average_row:.6f}s",
        flush=True,
    )
    print("slowest-rows: top=5", flush=True)
    for rank, (elapsed, page, column, row, text) in enumerate(
        sorted(timings, reverse=True)[:5], start=1
    ):
        print(
            f"slowest-row: rank={rank} page={page} column={column} row={row} "
            f"time={elapsed:.3f}s text={_short_text(text)!r}",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
