from __future__ import annotations

import argparse
import html
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, _page_from_row, read_jsonl, source_for_page
from .ocr_probe_exact_article import build_exact_article, row_starts_headword
from .ocr_probe_row_glyphs import analyse_row_exact
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def canonical_printed_text(value: object) -> str:
    """Canonicalise JSONL transcription for comparison with printed glyph OCR.

    SAOL14 JSONL uses + where the facsimile prints ~. Formatting tags are
    metadata rather than printed characters, so they are ignored here.
    Superscript digit glyphs are separate rasters but compare lexically as the
    corresponding digit used inside JSONL ``<sup>`` markup.
    """
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub("", text)
    text = text.translate(SUPERSCRIPT_TRANSLATION)
    text = text.replace("+", "~")
    return SPACE_RE.sub(" ", text).strip()


def _has_real_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.casefold() != "(null)"


def text_prefix_matches(recovered: str, reference: str) -> bool:
    """True when OCR agrees for every character present in JSONL ``text``."""
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
        crop = page.crop(box).convert("L")
        result = analyse_row_exact(crop, models, threshold=threshold)
        output.append(
            {
                "row": row_index,
                "matches": result["selected"],
                "ink": result["ink"],
                "fully_exact": result["fully_exact"],
                "covered_pixels": result["covered_pixels"],
                "source_pixels": result["source_pixels"],
            }
        )
        if progress is not None:
            progress(column, row_index + 1, len(physical_rows))
    return output


def recovered_page_articles(page, row_map: dict, models, *, threshold: int = 210, progress=None) -> list[dict]:
    articles: list[dict] = []
    for column, column_entry in enumerate(row_map["columns"]):
        rows = _analyse_column_rows(
            page,
            column_entry,
            column,
            models,
            threshold=threshold,
            progress=progress,
        )
        starts = [index for index, row in enumerate(rows) if row_starts_headword(row["matches"])]
        for pos, start in enumerate(starts):
            end = starts[pos + 1] if pos + 1 < len(starts) else len(rows)
            article = build_exact_article(rows[start:end])
            article["column"] = column
            article["start_row"] = start
            articles.append(article)
    return articles


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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare pixel-recovered SAOL article text with the available JSONL text prefix on one page."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--show-ok", action="store_true")
    args = ap.parse_args()

    rows = list(read_jsonl(args.jsonl))
    source = source_for_page(rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    print(f"page={args.page}: segmenterar fysiska rader ...", file=sys.stderr, flush=True)
    row_map = segment_page_rows(page, threshold=args.threshold)
    column_sizes = [len(column.get("rows") or []) for column in row_map["columns"]]
    total_rows = sum(column_sizes)
    completed_before = [sum(column_sizes[:column]) for column in range(len(column_sizes))]
    last_reported = {-1}

    def show_progress(column: int, row_done: int, column_total: int) -> None:
        done = completed_before[column] + row_done
        percent = int(100 * done / total_rows) if total_rows else 100
        bucket = percent // 5
        marker = (column, bucket)
        if marker not in last_reported or row_done in {1, column_total}:
            last_reported.add(marker)
            print(
                f"page={args.page}: {done}/{total_rows} rader ({percent:3d}%) "
                f"kolumn={column} rad={row_done}/{column_total}",
                file=sys.stderr,
                flush=True,
            )

    print(
        f"page={args.page}: analyserar {total_rows} rader i {len(column_sizes)} kolumner ...",
        file=sys.stderr,
        flush=True,
    )
    articles = recovered_page_articles(
        page,
        row_map,
        load_facit(args.facit),
        threshold=args.threshold,
        progress=show_progress,
    )
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
