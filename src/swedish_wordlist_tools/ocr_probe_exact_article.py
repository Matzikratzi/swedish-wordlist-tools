from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact, exact_text_runs, render_exact_text
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box

SUPERSCRIPT_DIGITS = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
}


def _sorted_matches(matches):
    return sorted(matches, key=lambda match: (match.x, match.baseline, match.label, match.style))


def _is_superscript_digit(match) -> bool:
    return match.label in SUPERSCRIPT_DIGITS


def row_starts_headword(matches) -> bool:
    rows = _sorted_matches(matches)
    index = 0
    while index < len(rows) and _is_superscript_digit(rows[index]):
        index += 1
    return index < len(rows) and rows[index].style == "bold"


def _initial_headword_end(matches) -> int:
    rows = _sorted_matches(matches)
    index = 0
    while index < len(rows) and _is_superscript_digit(rows[index]):
        index += 1
    while index < len(rows) and rows[index].style == "bold":
        index += 1
    return index


def _flatten(article_rows: list[dict]) -> list[tuple[int, object]]:
    flattened: list[tuple[int, object]] = []
    for row_index, row in enumerate(article_rows):
        for match in _sorted_matches(row["matches"]):
            flattened.append((row_index, match))
    return flattened


def _wrap_run(text: str, style: str, *, markup: bool) -> str:
    if not markup:
        return text
    if style == "bold":
        return f"<b>{text}</b>"
    if style == "italic":
        return f"<i>{text}</i>"
    return text


def _render_saol_matches(matches, source_ink, *, markup: bool) -> tuple[str, int]:
    """Render exact glyphs while preserving SAOL-specific spacing evidence.

    The normal renderer trusts measured blank columns.  SAOL inflection notation
    additionally guarantees that a new ``~`` token is preceded by whitespace.
    If the measured geometry misses that whitespace, insert it in the semantic
    rendering but count the insertion as a diagnostic rather than hiding it.

    Superscript digits are separate exact glyph models (for example ``¹``), so
    their smaller/raised raster remains distinct from an ordinary digit.  In
    markup output they are serialized as ``<sup>1</sup>`` etc.
    """
    runs = exact_text_runs(matches, source_ink=source_ink)
    pieces: list[str] = []
    previous_logical = ""
    forced_spaces = 0
    for run in runs:
        text = run["text"]
        style = run["style"]
        if style == "space":
            pieces.append(text)
            if text:
                previous_logical = text[-1]
            continue

        transformed: list[str] = []
        for ch in text:
            if ch == "~" and previous_logical and not previous_logical.isspace() and previous_logical != "~":
                transformed.append(" ")
                previous_logical = " "
                forced_spaces += 1
            if markup and ch in SUPERSCRIPT_DIGITS:
                transformed.append(f"<sup>{SUPERSCRIPT_DIGITS[ch]}</sup>")
            else:
                transformed.append(ch)
            previous_logical = ch
        pieces.append(_wrap_run("".join(transformed), style, markup=markup))
    return "".join(pieces), forced_spaces


def _render_range_with_diagnostics(
    article_rows: list[dict], start: int, end: int, *, markup: bool
) -> tuple[str, int]:
    if start >= end:
        return "", 0
    cursor = 0
    pieces: list[str] = []
    forced_spaces = 0
    for row in article_rows:
        matches = _sorted_matches(row["matches"])
        row_start = cursor
        row_end = cursor + len(matches)
        take_start = max(start, row_start)
        take_end = min(end, row_end)
        if take_start < take_end:
            selected = matches[take_start - row_start : take_end - row_start]
            piece, forced = _render_saol_matches(selected, row.get("ink"), markup=markup)
            piece = piece.strip()
            if piece:
                pieces.append(piece)
            forced_spaces += forced
        cursor = row_end
        if cursor >= end:
            break
    return " ".join(pieces), forced_spaces


def _render_range(article_rows: list[dict], start: int, end: int, *, markup: bool) -> str:
    return _render_range_with_diagnostics(article_rows, start, end, markup=markup)[0]


def build_exact_article(rows: list[dict]) -> dict:
    """Build one SAOL article from consecutive exact physical rows.

    The first row must start with a bold headword, optionally preceded by a
    superscript homonym digit. A later physical row with the same shape begins
    the next article and is not consumed. Digits do not end an article: once
    the first numbered explanation begins, the remaining physical rows still
    belong to the article until the next headword.

    The JSONL-like ``text`` field still ends when explanation text begins, at
    either the raised ¤ marker or the first ordinary numbered explanation. This
    keeps field boundaries separate from article boundaries.
    """
    if not rows:
        raise ValueError("article needs at least one physical row")
    if not row_starts_headword(rows[0].get("matches") or []):
        raise ValueError("first physical row does not start with a bold headword")

    article_rows = [rows[0]]
    for row in rows[1:]:
        if row_starts_headword(row.get("matches") or []):
            break
        article_rows.append(row)

    flat = _flatten(article_rows)
    first_row_matches = _sorted_matches(article_rows[0]["matches"])
    headword_end = _initial_headword_end(first_row_matches)

    text_start = next(
        (index for index, (_row_index, match) in enumerate(flat[headword_end:], start=headword_end) if match.style == "italic"),
        len(flat),
    )

    explanation_start = len(flat)
    explanation_reason = None
    for index, (_row_index, match) in enumerate(flat[text_start:], start=text_start):
        if match.label == "¤":
            explanation_start = index
            explanation_reason = "explanation-marker"
            break
        if match.label.isdigit():
            explanation_start = index
            explanation_reason = "numbered-explanation"
            break

    markup, forced_spaces = _render_range_with_diagnostics(article_rows, 0, len(flat), markup=True)
    return {
        "rows_consumed": len(article_rows),
        "fully_exact": all(bool(row.get("fully_exact", True)) for row in article_rows),
        "stycke": _render_range(article_rows, 0, headword_end, markup=False),
        "ordkl": _render_range(article_rows, headword_end, explanation_start, markup=True),
        "text": _render_range(article_rows, text_start, explanation_start, markup=False),
        "boundary": explanation_reason,
        "remainder": _render_range(article_rows, explanation_start, len(flat), markup=True),
        "markup": markup,
        "forced_space_before_tilde": forced_spaces,
    }


def _analyse_page_rows(page, column_entry: dict, start_row: int, models, *, threshold: int) -> list[dict]:
    physical_rows = column_entry.get("rows") or []
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    output: list[dict] = []
    for row_index in range(start_row, len(physical_rows)):
        row = physical_rows[row_index]
        box = _row_crop_box(
            row,
            column=int(column_entry["index"]),
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
                "page_top": int(row["page_top"]),
                "page_bottom": int(row["page_bottom"]),
                "matches": result["selected"],
                "ink": result["ink"],
                "fully_exact": result["fully_exact"],
                "covered_pixels": result["covered_pixels"],
                "source_pixels": result["source_pixels"],
            }
        )
        if row_index > start_row and row_starts_headword(result["selected"]):
            break
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconstruct one exact SAOL article across physical pixel-owned rows.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True, help="physical row containing the bold headword")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    row_map = segment_page_rows(page, threshold=args.threshold)
    column_entry = row_map["columns"][args.column]
    column_entry = dict(column_entry)
    column_entry["index"] = args.column
    rows = _analyse_page_rows(page, column_entry, args.row, load_facit(args.facit), threshold=args.threshold)
    article = build_exact_article(rows)

    print(
        f"page={args.page} column={args.column} start_row={args.row} "
        f"rows_consumed={article['rows_consumed']} fully_exact={article['fully_exact']} "
        f"forced_space_before_tilde={article['forced_space_before_tilde']}"
    )
    for row in rows[: article["rows_consumed"]]:
        print(
            f"row={row['row']} y={row['page_top']}..{row['page_bottom']} "
            f"covered={row['covered_pixels']}/{row['source_pixels']} fully_exact={row['fully_exact']} "
            f"text={render_exact_text(row['matches'], source_ink=row['ink'])}"
        )
    print(f"stycke={article['stycke']}")
    print(f"ordkl={article['ordkl']}")
    print(f"jsonl_text={article['text']}")
    print(f"boundary={article['boundary']}")
    print(f"remainder={article['remainder']}")
    print(f"markup={article['markup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
