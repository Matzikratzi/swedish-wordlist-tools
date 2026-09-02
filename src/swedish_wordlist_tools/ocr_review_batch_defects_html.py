from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

from . import ocr_review_five_rows_glyphs_boundary_html as boundary
from . import ocr_review_five_rows_glyphs_html as ui
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


def scan_context(context: dict, models, *, progress=None) -> dict:
    """Return only settled pixel defects for one already-segmented page."""
    positions = list(context.get("positions") or [])
    defects: list[dict] = []
    source_pixels = 0
    covered_pixels = 0
    for done, position in enumerate(positions, start=1):
        state = _load_review_state_for_audit(context, position, models)
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
        if progress is not None:
            progress(done, len(positions), position)
    return {
        "page": int(context["page_number"]),
        "rows_total": len(positions),
        "rows_exact": len(positions) - len(defects),
        "defects": defects,
        "source_pixels": source_pixels,
        "covered_pixels": covered_pixels,
        "unknown_pixels": source_pixels - covered_pixels,
    }


def scan_page(jsonl: Path, page: int, models, *, threshold: int = 210) -> dict:
    started = perf_counter()
    context = build_page_context(jsonl, page, threshold)
    last_bucket = -1

    def progress(done: int, total: int, position: tuple[int, int]) -> None:
        nonlocal last_bucket
        percent = int(100 * done / total) if total else 100
        bucket = percent // 10
        if bucket == last_bucket and done not in {1, total}:
            return
        last_bucket = bucket
        column, row = position
        print(
            f"batch page={page}: {done}/{total} ({percent:3d}%) col={column} row={row}",
            flush=True,
        )

    report = scan_context(context, models, progress=progress)
    report["elapsed"] = perf_counter() - started
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
            "then open only defective rows in the ordinary five-row editor."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="page selection, e.g. 7-12 or 7-10,14,18-20")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--scan-only", action="store_true", help="scan and summarize without starting the editor")
    args = ap.parse_args()

    try:
        pages = parse_pages(args.pages)
    except ValueError as exc:
        ap.error(str(exc))

    models = load_facit(args.facit)
    reports: list[dict] = []
    batch_started = perf_counter()
    print(f"batch: skannar sidor {pages}; bara pixeldefekter räknas", flush=True)
    for page in pages:
        report = scan_page(args.jsonl, page, models, threshold=args.threshold)
        reports.append(report)
        status = "EXAKT" if not report["defects"] else f"TRASIG {len(report['defects'])} rader"
        print(
            f"batch page={page}: {status}; rows_exact={report['rows_exact']}/{report['rows_total']} "
            f"unknown_pixels={report['unknown_pixels']} elapsed={_format_duration(report['elapsed'])}",
            flush=True,
        )

    defective_reports = [report for report in reports if report["defects"]]
    total_defects = sum(len(report["defects"]) for report in defective_reports)
    print(
        f"batch: klart på {_format_duration(perf_counter() - batch_started)}; "
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

    if not defective_reports or args.scan_only:
        if not defective_reports:
            print("batch: inga trasiga rader på de valda sidorna", flush=True)
        return 0

    first_report = defective_reports[0]
    first_defect = first_report["defects"][0]
    return launch_editor(
        args.jsonl,
        page=int(first_report["page"]),
        position=(int(first_defect["column"]), int(first_defect["row"])),
        threshold=args.threshold,
        facit=args.facit,
        host=args.host,
        port=args.port,
        no_browser=args.no_browser,
    )


if __name__ == "__main__":
    raise SystemExit(main())
