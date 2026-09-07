from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

from . import ocr_review_five_rows_glyphs_boundary_html as boundary
from . import ocr_review_five_rows_glyphs_html as ui
from .ocr_batch_progress_cache import BatchProgressStore, DEFAULT_CACHE_PATH
from .ocr_compare_page_text_prefix import _format_duration
from .ocr_glyph_matcher import load_facit
from .ocr_page_glyph_audit import _load_review_state_for_audit
from .ocr_review_five_rows_glyphs_fast_html import build_page_context


def parse_pages(spec: str) -> list[int]:
    """Parse e.g. ``7-10,12,15-16`` into sorted unique page numbers."""
    pages: set[int] = set()
    for raw_part in str(spec).split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start = int(left)
            stop = int(right)
            if start <= 0 or stop <= 0:
                raise ValueError("page numbers must be positive")
            if stop < start:
                raise ValueError(f"descending page range is not allowed: {part!r}")
            pages.update(range(start, stop + 1))
        else:
            page = int(part)
            if page <= 0:
                raise ValueError("page numbers must be positive")
            pages.add(page)
    if not pages:
        raise ValueError("no pages selected")
    return sorted(pages)


def scan_context(
    context: dict,
    models,
    *,
    progress=None,
    stop_after_first_defect: bool = False,
    start_index: int = 0,
    exact_callback=None,
) -> dict:
    """Scan settled rows, optionally resuming inside the page.

    ``start_index`` is a zero-based physical-row frontier.  ``exact_callback``
    is called after every exact row with the next safe index, allowing the
    persistent batch cache to survive Ctrl-C or a later editor session.
    """
    positions = list(context.get("positions") or [])
    start_index = max(0, min(len(positions), int(start_index)))
    defects: list[dict] = []
    source_pixels = 0
    covered_pixels = 0
    rows_scanned_this_run = 0
    last_done = start_index

    for done, position in enumerate(positions[start_index:], start=start_index + 1):
        state = _load_review_state_for_audit(context, position, models)
        last_done = done
        rows_scanned_this_run += 1
        source = int(state.get("source_pixels") or 0)
        covered = int(state.get("covered_pixels") or 0)
        unknown = max(0, source - covered)
        source_pixels += source
        covered_pixels += covered
        if unknown:
            defects.append(
                {
                    "column": int(state["column"]),
                    "row": int(state["row"]),
                    "unknown_pixels": unknown,
                    "covered_pixels": covered,
                    "source_pixels": source,
                    "text": str(state.get("text") or ""),
                }
            )
        else:
            if exact_callback is not None:
                exact_callback(done, position)
        if progress is not None:
            progress(done, len(positions), position)
        if unknown and stop_after_first_defect:
            break

    complete_scan = last_done == len(positions) and not defects
    return {
        "page": int(context["page_number"]),
        "rows_total": len(positions),
        "start_index": start_index,
        "next_index": last_done,
        "rows_scanned": rows_scanned_this_run,
        "complete_scan": complete_scan,
        "rows_exact": rows_scanned_this_run - len(defects),
        "defects": defects,
        "source_pixels": source_pixels,
        "covered_pixels": covered_pixels,
        "unknown_pixels": source_pixels - covered_pixels,
    }


def scan_page(
    jsonl: Path,
    page: int,
    models,
    *,
    threshold: int = 210,
    stop_after_first_defect: bool = False,
    progress_store: BatchProgressStore | None = None,
) -> dict:
    started = perf_counter()
    context = build_page_context(jsonl, page, threshold)
    positions = list(context.get("positions") or [])
    source_digest = boundary.page_digest(context["page"])
    start_index = 0
    cached_complete = False

    if progress_store is not None:
        start_index, cached_complete = progress_store.resume_index(
            page=page,
            threshold=threshold,
            source_digest=source_digest,
            row_count=len(positions),
            models=models,
        )
        if cached_complete:
            return {
                "page": page,
                "rows_total": len(positions),
                "start_index": len(positions),
                "next_index": len(positions),
                "rows_scanned": 0,
                "complete_scan": True,
                "rows_exact": len(positions),
                "defects": [],
                "source_pixels": 0,
                "covered_pixels": 0,
                "unknown_pixels": 0,
                "elapsed": perf_counter() - started,
                "cached_complete": True,
            }
        if start_index:
            column, row = positions[start_index]
            print(
                f"batch page={page}: återupptar vid {start_index + 1}/{len(positions)} "
                f"col={column} row={row} (en rad rewind för säker radgräns)",
                flush=True,
            )

    last_bucket = -1

    def progress(done: int, total: int, position: tuple[int, int]) -> None:
        nonlocal last_bucket
        percent = int(100 * done / total) if total else 100
        bucket = percent // 10
        if bucket == last_bucket and done not in {start_index + 1, total}:
            return
        last_bucket = bucket
        column, row = position
        print(
            f"batch page={page}: {done}/{total} ({percent:3d}%) col={column} row={row}",
            flush=True,
        )

    def exact_callback(next_index: int, _position: tuple[int, int]) -> None:
        if progress_store is None:
            return
        progress_store.save_frontier(
            page=page,
            threshold=threshold,
            source_digest=source_digest,
            row_count=len(positions),
            next_index=next_index,
            models=models,
            complete=False,
        )

    report = scan_context(
        context,
        models,
        progress=progress,
        stop_after_first_defect=stop_after_first_defect,
        start_index=start_index,
        exact_callback=exact_callback,
    )
    if report["complete_scan"] and progress_store is not None:
        progress_store.save_frontier(
            page=page,
            threshold=threshold,
            source_digest=source_digest,
            row_count=len(positions),
            next_index=len(positions),
            models=models,
            complete=True,
        )
    report["elapsed"] = perf_counter() - started
    report["cached_complete"] = False
    return report


def defect_url(host: str, port: int, position: tuple[int, int]) -> str:
    return f"http://{host}:{port}{ui.row_url(position, mode='defects', anchor=position)}"


def editor_argv(
    jsonl: Path,
    *,
    page: int,
    position: tuple[int, int],
    threshold: int,
    facit: Path,
    host: str,
    port: int,
    no_browser: bool,
) -> list[str]:
    column, row = position
    out = [
        "ocr_review_five_rows_glyphs_boundary_html",
        str(jsonl),
        "--page",
        str(page),
        "--column",
        str(column),
        "--row",
        str(row),
        "--threshold",
        str(threshold),
        "--facit",
        str(facit),
        "--host",
        str(host),
        "--port",
        str(port),
    ]
    if no_browser:
        out.append("--no-browser")
    return out


def launch_editor(
    jsonl: Path,
    *,
    page: int,
    position: tuple[int, int],
    threshold: int,
    facit: Path,
    host: str,
    port: int,
    no_browser: bool,
) -> int:
    """Launch the ordinary boundary editor, but open it directly in defect mode."""
    wanted_url = defect_url(host, port, position)
    print(f"batch: öppnar vanliga editorn i defects-läge: {wanted_url}", flush=True)
    old_argv = sys.argv
    browser_module = boundary.fast.webbrowser
    old_open = browser_module.open

    def open_defects(_url, *args, **kwargs):
        return old_open(wanted_url, *args, **kwargs)

    try:
        sys.argv = editor_argv(
            jsonl,
            page=page,
            position=position,
            threshold=threshold,
            facit=facit,
            host=host,
            port=port,
            no_browser=no_browser,
        )
        browser_module.open = open_defects
        return boundary.main()
    finally:
        browser_module.open = old_open
        sys.argv = old_argv


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Scan several SAOL pages with the exact boundary-aware glyph pipeline, "
            "then open the first defective page immediately in the ordinary five-row editor."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="page selection, e.g. 7-12 or 7-10,14,18-20")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--scan-only", action="store_true", help="fully scan and summarize all selected pages without starting the editor")
    ap.add_argument("--progress-cache", type=Path, default=DEFAULT_CACHE_PATH)
    ap.add_argument("--reset-progress", action="store_true", help="discard saved batch progress before scanning")
    args = ap.parse_args()

    try:
        pages = parse_pages(args.pages)
    except ValueError as exc:
        ap.error(str(exc))

    models = load_facit(args.facit)
    progress_store = BatchProgressStore(args.progress_cache)
    if args.reset_progress:
        progress_store.clear()
        print(f"batch: rensade progress-cache {args.progress_cache}", flush=True)

    batch_started = perf_counter()
    print(
        f"batch: skannar sidor {pages}; bara pixeldefekter räknas; "
        + ("full scan" if args.scan_only else "öppnar direkt vid första defekt")
        + f"; progress-cache={args.progress_cache}",
        flush=True,
    )

    if not args.scan_only:
        exact_pages = 0
        for page in pages:
            report = scan_page(
                args.jsonl,
                page,
                models,
                threshold=args.threshold,
                stop_after_first_defect=True,
                progress_store=progress_store,
            )
            if report["defects"]:
                first = report["defects"][0]
                print(
                    f"batch page={page}: TRASIG; hittade första defekten efter "
                    f"{report['rows_scanned']} nya rader, "
                    f"unknown={first['unknown_pixels']} col={first['column']} row={first['row']} "
                    f"elapsed={_format_duration(report['elapsed'])} text={first['text']!r}",
                    flush=True,
                )
                print(
                    f"batch: {exact_pages} föregående sida/sidor var pixel-exakta eller cachade; "
                    f"slutar förskanna efter {_format_duration(perf_counter() - batch_started)}",
                    flush=True,
                )
                return launch_editor(
                    args.jsonl,
                    page=page,
                    position=(int(first["column"]), int(first["row"])),
                    threshold=args.threshold,
                    facit=args.facit,
                    host=args.host,
                    port=args.port,
                    no_browser=args.no_browser,
                )

            exact_pages += 1
            if report.get("cached_complete"):
                print(f"batch page={page}: EXAKT (cachad; 0 rader omräknade)", flush=True)
            else:
                print(
                    f"batch page={page}: EXAKT; nya_rader={report['rows_scanned']} "
                    f"elapsed={_format_duration(report['elapsed'])}",
                    flush=True,
                )

        print(
            f"batch: inga trasiga rader på de valda sidorna; pages={len(pages)} "
            f"elapsed={_format_duration(perf_counter() - batch_started)}",
            flush=True,
        )
        return 0

    reports: list[dict] = []
    for page in pages:
        report = scan_page(
            args.jsonl,
            page,
            models,
            threshold=args.threshold,
            progress_store=progress_store,
        )
        reports.append(report)
        status = "EXAKT" if not report["defects"] else f"TRASIG {len(report['defects'])} rader"
        print(
            f"batch page={page}: {status}; nya_rader={report['rows_scanned']} "
            f"unknown_pixels={report['unknown_pixels']} elapsed={_format_duration(report['elapsed'])}",
            flush=True,
        )

    defective_reports = [report for report in reports if report["defects"]]
    total_defects = sum(len(report["defects"]) for report in defective_reports)
    print(
        f"batch: full scan klar på {_format_duration(perf_counter() - batch_started)}; "
        f"pages={len(reports)} exact_pages={len(reports) - len(defective_reports)} "
        f"defective_pages={len(defective_reports)} defective_rows={total_defects}",
        flush=True,
    )
    for report in defective_reports:
        first = report["defects"][0]
        print(
            f"BROKEN-PAGE page={report['page']} rows={len(report['defects'])} "
            f"first=col{first['column']}/row{first['row']} unknown={first['unknown_pixels']} "
            f"text={first['text']!r}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
