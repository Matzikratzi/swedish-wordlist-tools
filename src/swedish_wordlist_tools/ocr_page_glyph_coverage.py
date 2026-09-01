from __future__ import annotations

import argparse
import html
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from time import perf_counter

from . import ocr_column_row_segmentation as segmentation_module
from . import ocr_glyph_gap_matcher as gap_matcher_module
from . import ocr_glyph_matcher as matcher_module
from . import ocr_probe_row_glyphs_grouped as grouped_probe_module
from . import ocr_row_map_words as row_map_module
from .ocr_column_row_segmentation import segment_page_rows
from .ocr_compare_page_text_prefix import (
    _format_duration,
    _headword_key,
    _reference_headword,
    analyse_page_rows,
    articles_from_analysed_rows,
    canonical_printed_text,
    text_prefix_matches,
)
from .ocr_glyph_matcher import load_facit
from .ocr_page_analysis_cache import (
    DEFAULT_CACHE_DIR,
    geometry_cache_key,
    glyph_cache_key,
    load_or_compute,
)
from .ocr_prepare_sequential_page import _load_source_image, _page_from_row, read_jsonl, source_for_page

LEADING_SUP_RE = re.compile(r"^\s*<sup>\s*([0-9]+)\s*</sup>\s*", re.IGNORECASE)


def _has_real_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.casefold() != "(null)"


def reference_headword_key(row: dict) -> str:
    """Return the printed headword key, using JSONL homonr when available.

    ``homonr`` is authoritative for homonym numbering.  ``stycke`` still gives
    us the printed base headword, including SAOL boundary marks such as ``·``.
    This avoids relying on the serialized ``<sup>N</sup>`` markup for the number.
    """
    headword = html.unescape(_reference_headword(row))
    homonr = str(row.get("homonr") or "").strip()
    if homonr:
        base = LEADING_SUP_RE.sub("", headword, count=1)
        return _headword_key(f"{homonr}{base}")
    return _headword_key(headword)


def glyph_coverage_report(columns: list[list[dict]]) -> dict:
    """Summarise whether every source ink pixel belongs to a known glyph raster.

    This intentionally covers *all* segmented body-row ink, including
    pronunciation, explanations, and printed material after the JSONL text
    prefix ends.  Coverage says that the raster is known; it does not claim that
    the glyph label is semantically verified by JSONL outside the available
    facit fields.
    """
    source_pixels = 0
    covered_pixels = 0
    rows_total = 0
    rows_exact = 0
    misses: list[dict] = []

    for column, rows in enumerate(columns):
        for row in rows:
            rows_total += 1
            source = int(row.get("source_pixels") or 0)
            covered = int(row.get("covered_pixels") or 0)
            unknown = max(0, source - covered)
            source_pixels += source
            covered_pixels += covered
            if unknown == 0:
                rows_exact += 1
            else:
                misses.append(
                    {
                        "column": column,
                        "row": int(row.get("row") or 0),
                        "source_pixels": source,
                        "covered_pixels": covered,
                        "unknown_pixels": unknown,
                    }
                )

    misses.sort(key=lambda item: (-item["unknown_pixels"], item["column"], item["row"]))
    return {
        "rows_total": rows_total,
        "rows_exact": rows_exact,
        "source_pixels": source_pixels,
        "covered_pixels": covered_pixels,
        "unknown_pixels": max(0, source_pixels - covered_pixels),
        "misses": misses,
    }


def compare_available_facit(rows: list[dict], articles: list[dict], page_number: int) -> dict:
    """Verify only what JSONL can actually tell us, independently of coverage.

    Every JSONL headword participates, including entries whose ``text`` is
    ``(null)``.  For entries with text we require only that the recovered print
    starts with the available JSONL text string.  We never use text beyond that
    stored prefix as correction facit.  This naturally respects the source
    export's truncation rule because the stored ``text`` value itself is the
    comparison boundary.
    """
    references = [row for row in rows if _page_from_row(row) == page_number]
    by_headword: dict[str, deque[dict]] = defaultdict(deque)
    for row in references:
        by_headword[reference_headword_key(row)].append(row)

    results: list[dict] = []
    matched_reference_ids: set[int] = set()
    for article in articles:
        key = _headword_key(article.get("stycke") or "")
        queue = by_headword.get(key)
        reference = queue.popleft() if queue else None
        if reference is None:
            continue

        matched_reference_ids.add(id(reference))
        has_text = _has_real_text(reference.get("text"))
        expected = canonical_printed_text(reference.get("text")) if has_text else ""
        recovered = canonical_printed_text(article.get("text"))
        results.append(
            {
                "headword": _reference_headword(reference),
                "homonr": str(reference.get("homonr") or ""),
                "column": article.get("column"),
                "row": article.get("start_row"),
                "has_text": has_text,
                "expected": expected,
                "recovered": recovered,
                "prefix_exact": text_prefix_matches(recovered, expected) if has_text else None,
            }
        )

    unmatched = [row for row in references if id(row) not in matched_reference_ids]
    with_text = [item for item in results if item["has_text"]]
    exact_text = [item for item in with_text if item["prefix_exact"]]
    references_with_text = [row for row in references if _has_real_text(row.get("text"))]
    return {
        "references_total": len(references),
        "references_with_text": len(references_with_text),
        "matched_headwords": len(results),
        "matched_with_text": len(with_text),
        "text_prefix_exact": len(exact_text),
        "unmatched_references": len(unmatched),
        "results": results,
        "unmatched": unmatched,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Report whole-page exact glyph-raster coverage separately from the "
            "portion that can be verified against SAOL14 JSONL."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--no-cache", action="store_true", help="ignore persistent page caches for this run")
    ap.add_argument(
        "--show-pixel-misses",
        action="store_true",
        help="list every physical row that still contains pixels not owned by a known glyph raster",
    )
    ap.add_argument(
        "--show-facit",
        action="store_true",
        help="show every matched JSONL headword, including entries whose text is (null)",
    )
    args = ap.parse_args()

    rows = list(read_jsonl(args.jsonl))
    source = source_for_page(rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    print(f"page={args.page}: segmenterar fysiska rader ...", file=sys.stderr, flush=True)
    geometry_key = geometry_cache_key(
        page,
        threshold=args.threshold,
        segmentation_module_file=segmentation_module.__file__,
    )
    if args.no_cache:
        row_map = segment_page_rows(page, threshold=args.threshold)
    else:
        row_map, geometry_hit, geometry_path = load_or_compute(
            args.cache_dir,
            args.page,
            "geometry",
            geometry_key,
            lambda: segment_page_rows(page, threshold=args.threshold),
        )
        print(
            f"page={args.page}: geometri-cache {'HIT' if geometry_hit else 'MISS'} {geometry_path}",
            file=sys.stderr,
            flush=True,
        )

    column_sizes = [len(column.get("rows") or []) for column in row_map["columns"]]
    total_rows = sum(column_sizes)
    completed_before = [sum(column_sizes[:column]) for column in range(len(column_sizes))]
    reported: set[tuple[int, int]] = set()
    analysis_started = perf_counter()

    def show_progress(column: int, row_done: int, column_total: int) -> None:
        done = completed_before[column] + row_done
        percent = int(100 * done / total_rows) if total_rows else 100
        marker = (column, percent // 5)
        if marker in reported and row_done not in {1, column_total}:
            return
        reported.add(marker)
        elapsed = perf_counter() - analysis_started
        eta = elapsed * (total_rows - done) / done if done else 0.0
        rate = done / elapsed if elapsed > 0 else 0.0
        print(
            f"page={args.page}: {done}/{total_rows} rader ({percent:3d}%) "
            f"kolumn={column} rad={row_done}/{column_total} "
            f"elapsed={_format_duration(elapsed)} eta={_format_duration(eta)} rate={rate:.2f} rad/s",
            file=sys.stderr,
            flush=True,
        )

    models = load_facit(args.facit)
    print(
        f"page={args.page}: analyserar {total_rows} rader i {len(column_sizes)} kolumner "
        f"med grupperad glyphmatchning ...",
        file=sys.stderr,
        flush=True,
    )
    if args.no_cache:
        analysed_columns = analyse_page_rows(page, row_map, models, threshold=args.threshold, progress=show_progress)
    else:
        glyph_key = glyph_cache_key(
            geometry_key,
            args.facit,
            matcher_module_file=matcher_module.__file__,
            row_probe_module_file=grouped_probe_module.__file__,
            row_map_module_file=row_map_module.__file__,
            extra_module_files=(gap_matcher_module.__file__,),
        )
        analysed_columns, glyph_hit, glyph_path = load_or_compute(
            args.cache_dir,
            args.page,
            "glyphs",
            glyph_key,
            lambda: analyse_page_rows(page, row_map, models, threshold=args.threshold, progress=show_progress),
        )
        print(
            f"page={args.page}: glyph-cache {'HIT' if glyph_hit else 'MISS'} {glyph_path}",
            file=sys.stderr,
            flush=True,
        )

    analysis_seconds = perf_counter() - analysis_started
    print(
        f"page={args.page}: glyphanalys klar på {_format_duration(analysis_seconds)}",
        file=sys.stderr,
        flush=True,
    )

    coverage = glyph_coverage_report(analysed_columns)
    articles = articles_from_analysed_rows(analysed_columns)
    facit = compare_available_facit(rows, articles, args.page)

    source_pixels = coverage["source_pixels"]
    coverage_rate = 100.0 * coverage["covered_pixels"] / source_pixels if source_pixels else 100.0
    print(
        f"page={args.page} glyph_rows_exact={coverage['rows_exact']}/{coverage['rows_total']} "
        f"glyph_pixels={coverage['covered_pixels']}/{source_pixels} "
        f"glyph_coverage={coverage_rate:.2f}% unknown_pixels={coverage['unknown_pixels']}"
    )
    print(
        f"page={args.page} jsonl_headwords={facit['matched_headwords']}/{facit['references_total']} "
        f"matched_with_text={facit['matched_with_text']}/{facit['references_with_text']} "
        f"text_prefix_exact={facit['text_prefix_exact']}/{facit['matched_with_text']} "
        f"unmatched_references={facit['unmatched_references']}"
    )
    print(
        "scope: glyph_coverage=all segmented body-row ink; "
        "jsonl_verification=headword (homonr authoritative) + available text prefix only"
    )
    print(
        "scope: pronunciation, explanations after ¤/number, and print after JSONL truncation "
        "must still have known glyph rasters but are not label-corrected from JSONL"
    )

    if coverage["misses"]:
        print(f"pixel_rows_with_unknown={len(coverage['misses'])}")
        misses = coverage["misses"] if args.show_pixel_misses else coverage["misses"][:10]
        for item in misses:
            print(
                f"PIXEL-MISS\tcol={item['column']} row={item['row']} "
                f"unknown={item['unknown_pixels']} "
                f"covered={item['covered_pixels']}/{item['source_pixels']}"
            )
        if not args.show_pixel_misses and len(coverage["misses"]) > len(misses):
            print(
                f"... {len(coverage['misses']) - len(misses)} fler rader; "
                "kör med --show-pixel-misses för hela listan"
            )

    for item in facit["results"]:
        should_show = args.show_facit or (item["has_text"] and not item["prefix_exact"])
        if not should_show:
            continue
        status = "NO-TEXT" if not item["has_text"] else ("OK" if item["prefix_exact"] else "MISS")
        print(
            f"{status}\tcol={item['column']} row={item['row']} homonr={item['homonr']!r} "
            f"head={item['headword']!r}"
        )
        if item["has_text"]:
            print(f"  jsonl={item['expected']!r}")
            print(f"  ocr  ={item['recovered']!r}")

    if facit["unmatched"]:
        print("UNMATCHED JSONL HEADWORDS")
        for row in facit["unmatched"]:
            print(
                f"  homonr={str(row.get('homonr') or '')!r} "
                f"head={_reference_headword(row)!r} text={canonical_printed_text(row.get('text'))!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
