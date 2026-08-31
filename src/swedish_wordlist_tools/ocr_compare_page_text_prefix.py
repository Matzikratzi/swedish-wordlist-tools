from __future__ import annotations

import argparse
import html
import re
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


def canonical_printed_text(value: object) -> str:
    """Canonicalise JSONL transcription for comparison with printed glyph OCR.

    SAOL14 JSONL uses + where the facsimile prints ~.  Formatting tags are
    metadata rather than printed characters, so they are ignored here.  Other
    punctuation is deliberately preserved: this comparison is meant to be
    strict apart from that known notation translation and whitespace folding.
    """
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub("", text)
    text = text.replace("+", "~")
    return SPACE_RE.sub(" ", text).strip()


def text_prefix_matches(recovered: str, reference: str) -> bool:
    """True when OCR agrees for every character present in JSONL ``text``."""
    wanted = canonical_printed_text(reference)
    got = canonical_printed_text(recovered)
    return bool(wanted) and got.startswith(wanted)


def _headword_key(value: object) -> str:
    return canonical_printed_text(value).casefold()


def _reference_headword(row: dict) -> str:
    return str(row.get("stycke") or row.get("ord") or row.get("normaliserat_ord") or "").strip()


def _analyse_column_rows(page, column_entry: dict, column: int, models, *, threshold: int) -> list[dict]:
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
    return output


def recovered_page_articles(page, row_map: dict, models, *, threshold: int = 210) -> list[dict]:
    articles: list[dict] = []
    for column, column_entry in enumerate(row_map["columns"]):
        rows = _analyse_column_rows(page, column_entry, column, models, threshold=threshold)
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
        if _page_from_row(row) == page_number and str(row.get("text") or "").strip()
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
            }
        )

    unmatched = [row for row in references if id(row) not in matched_reference_ids]
    exact = [item for item in results if item["prefix_exact"]]
    return {
        "references_with_text": len(references),
        "recovered_articles": len(articles),
        "matched_headwords": len(results),
        "text_prefix_exact": len(exact),
        "unmatched_references": len(unmatched),
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

    row_map = segment_page_rows(page, threshold=args.threshold)
    articles = recovered_page_articles(page, row_map, load_facit(args.facit), threshold=args.threshold)
    report = compare_page(rows, articles, args.page)

    print(
        f"page={args.page} references_with_text={report['references_with_text']} "
        f"recovered_articles={report['recovered_articles']} matched_headwords={report['matched_headwords']} "
        f"text_prefix_exact={report['text_prefix_exact']} unmatched_references={report['unmatched_references']}"
    )
    denominator = report["matched_headwords"]
    if denominator:
        print(f"matched_text_rate={100.0 * report['text_prefix_exact'] / denominator:.1f}%")

    for item in report["results"]:
        if item["prefix_exact"] and not args.show_ok:
            continue
        status = "OK" if item["prefix_exact"] else "MISS"
        print(
            f"{status}\tcol={item['column']} row={item['row']} exact_pixels={item['fully_exact']} "
            f"head={item['headword']!r}\n"
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
