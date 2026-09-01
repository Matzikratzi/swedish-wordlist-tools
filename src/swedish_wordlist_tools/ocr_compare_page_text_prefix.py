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
from .ocr_glyph_matcher import load_facit
from .ocr_page_analysis_cache import (
    DEFAULT_CACHE_DIR,
    geometry_cache_key,
    glyph_cache_key,
    load_or_compute,
)
from .ocr_prepare_sequential_page import _load_source_image, _page_from_row, read_jsonl, source_for_page
from .ocr_probe_exact_article import build_exact_article, row_starts_headword
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped
from .ocr_row_map_words import _owned_row_crop, _persistent_left_rule_x, _row_crop_box

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def canonical_printed_text(value: object) -> str:
    """Canonicalise JSONL transcription for comparison with printed glyph OCR."""
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub("", text)
    text = text.translate(SUPERSCRIPT_TRANSLATION)
    text = text.replace("+", "~")
    return SPACE_RE.sub(" ", text).strip()


def _has_real_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.casefold() != "(null)"


def text_prefix_matches(recovered: str, reference: str) -> bool:
    wanted = canonical_printed_text(reference)
    got = canonical_printed_text(recovered)
    return bool(wanted) and got.startswith(wanted)


def _headword_key(value: object) -> str:
    return canonical_printed_text(value).casefold()


def _reference_headword(row: dict) -> str:
    return str(row.get("stycke") or row.get("ord") or row.get("normaliserat_ord") or "").strip()


def _analyse_column_rows(
    page,
    column_entry: dict,
    column: int,
    models,
    *,
    threshold: int,
    progress=None,
) -> list[dict]:
    physical_rows = column_entry.get("rows") or []
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    output: list[dict] = []
    for row_index, row in enumerate(physical_rows):
        box = _row_crop_box(
            row,
            column=column,
            page_width=page.width,
            page_height=page.height,
            pad_y=1,
            left_override=content_left,
        )
        crop, removed_neighbor_pixels = _owned_row_crop(
            page,
            row,
            box,
            threshold=threshold,
        )
        result = analyse_row_exact_grouped(crop, models, threshold=threshold)
        output.append(
            {
                "row": row_index,
                "matches": result["selected"],
                "ink": result["ink"],
                "fully_exact": result["fully_exact"],
                "covered_pixels": result["covered_pixels"],
                "source_pixels": result["source_pixels"],
                "removed_neighbor_pixels": removed_neighbor_pixels,
            }
        )
        if progress is not None:
            progress(column, row_index + 1, len(physical_rows))
    return output


def analyse_page_rows(page, row_map: dict, models, *, threshold: int = 210, progress=None) -> list[list[dict]]:
    return [
        _analyse_column_rows(page, column_entry, column, models, threshold=threshold, progress=progress)
        for column, column_entry in enumerate(row_map["columns"])
    ]


def articles_from_analysed_rows(columns: list[list[dict]]) -> list[dict]:
    articles: list[dict] = []
    for column, rows in enumerate(columns):
        starts = [index for index, row in enumerate(rows) if row_starts_headword(row["matches"])]
        for pos, start in enumerate(starts):
            end = starts[pos + 1] if pos + 1 < len(starts) else len(rows)
            article = build_exact_article(rows[start:end])
            article["column"] = column
            article["start_row"] = start
            articles.append(article)
    return articles


def recovered_page_articles(page, row_map: dict, models, *, threshold: int = 210, progress=None) -> list[dict]:
    return articles_from_analysed_rows(
        analyse_page_rows(page, row_map, models, threshold=threshold, progress=progress)
    )


def compare_page(rows: list[dict], articles: list[dict], page_number: int) -> dict:
    references = [
        row for row in rows
        if _page_from_row(row) == page_number and _has_real_text(row.get("text"))
    ]
    by_headword: dict[str, deque[dict]] = defaultdict(deque)
    for row in references:
        by_headword[_headword_key(_reference_headword(row))].append(row)

    results: list[dict] = []
    matched_reference_ids: set[int] = set()
    for article in articles:
        key = _headword_key(article.get("stycke") or "")
        queue = by_headword.get(key)
        reference = queue.popleft() if queue else None
        if reference is None:
            continue
        matched_reference_ids.add(id(reference))
        expected = canonical_printed_text(reference.get("text"))
        recovered = canonical_printed_text(article.get("text"))
        results.append(
            {
                "headword": _reference_headword(reference),
                "column": article.get("column"),
                "row": article.get("start_row"),
                "fully_exact": bool(article.get("fully_exact")),
                "expected": expected,
                "recovered": recovered,
                "prefix_exact": text_prefix_matches(recovered, expected),
                "forced_space_before_tilde": int(article.get("forced_space_before_tilde") or 0),
            }
        )

    unmatched = [row for row in references if id(row) not in matched_reference_ids]
    exact = [item for item in results if item["prefix_exact"]]
    forced_spaces = sum(item["forced_space_before_tilde"] for item in results)
    forced_articles = sum(bool(item["forced_space_before_tilde"]) for item in results)
    return {
        "references_with_text": len(references),
        "recovered_articles": len(articles),
        "matched_headwords": len(results),
        "text_prefix_exact": len(exact),
        "unmatched_references": len(unmatched),
        "forced_space_before_tilde": forced_spaces,
        "articles_with_forced_tilde_space": forced_articles,
        "results": results,
        "unmatched": unmatched,
    }


def _format_duration(seconds: float) -> str:
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds + 0.5), 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{rest:02d}s"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare pixel-recovered SAOL article text with the available JSONL text prefix on one page."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--show-ok", action="store_true")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--no-cache", action="store_true", help="ignore persistent page caches for this run")
    args = ap.parse_args()

    rows = list(read_jsonl(args.jsonl))
    source = source_for_page(rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    print(f"page={args.page}: segmenterar fysiska rader ...", file=sys.stderr, flush=True)
    if args.no_cache:
        row_map = segment_page_rows(page, threshold=args.threshold)
        geometry_key = geometry_cache_key(page, threshold=args.threshold, segmentation_module_file=segmentation_module.__file__)
    else:
        geometry_key = geometry_cache_key(page, threshold=args.threshold, segmentation_module_file=segmentation_module.__file__)
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
    last_reported = {-1}
    analysis_started = perf_counter()

    def show_progress(column: int, row_done: int, column_total: int) -> None:
        done = completed_before[column] + row_done
        percent = int(100 * done / total_rows) if total_rows else 100
        bucket = percent // 5
        marker = (column, bucket)
        if marker not in last_reported or row_done in {1, column_total}:
            last_reported.add(marker)
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
    articles = articles_from_analysed_rows(analysed_columns)
    print(f"page={args.page}: jämför {len(articles)} återfunna artiklar med JSONL ...", file=sys.stderr, flush=True)
    report = compare_page(rows, articles, args.page)

    print(
        f"page={args.page} references_with_text={report['references_with_text']} "
        f"recovered_articles={report['recovered_articles']} matched_headwords={report['matched_headwords']} "
        f"text_prefix_exact={report['text_prefix_exact']} unmatched_references={report['unmatched_references']}"
    )
    print(
        f"forced_space_before_tilde={report['forced_space_before_tilde']} "
        f"articles_with_forced_tilde_space={report['articles_with_forced_tilde_space']}"
    )
    denominator = report["matched_headwords"]
    if denominator:
        print(f"matched_text_rate={100.0 * report['text_prefix_exact'] / denominator:.1f}%")

    for item in report["results"]:
        spacing_warning = item["forced_space_before_tilde"]
        if item["prefix_exact"] and not args.show_ok and not spacing_warning:
            continue
        if item["prefix_exact"] and spacing_warning:
            status = "OK+SPACE"
        else:
            status = "OK" if item["prefix_exact"] else "MISS"
        print(
            f"{status}\tcol={item['column']} row={item['row']} exact_pixels={item['fully_exact']} "
            f"forced_tilde_spaces={spacing_warning} head={item['headword']!r}\n"
            f"  jsonl={item['expected']!r}\n"
            f"  ocr  ={item['recovered']!r}"
        )

    if report["unmatched"]:
        print("UNMATCHED HEADWORDS")
        for row in report["unmatched"]:
            print(f"  {_reference_headword(row)!r}\ttext={canonical_printed_text(row.get('text'))!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
