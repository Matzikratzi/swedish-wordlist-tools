from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import exact_matches, load_facit, select_best_baseline_partition
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


def row_ink(crop, *, threshold: int = 210) -> set[tuple[int, int]]:
    gray = crop.convert("L")
    pixels = gray.load()
    return {
        (x, y)
        for y in range(gray.height)
        for x in range(gray.width)
        if pixels[x, y] < threshold
    }


def analyse_row_exact(crop, models, *, threshold: int = 210) -> dict:
    ink = row_ink(crop, threshold=threshold)
    baseline, selected = select_best_baseline_partition(ink, crop.width, crop.height, models)
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    return {
        "baseline": baseline,
        "source_pixels": len(ink),
        "covered_pixels": len(covered),
        "fully_exact": bool(ink) and covered == ink,
        "candidate_count": len(exact_matches(ink, crop.width, crop.height, models)),
        "selected": selected,
    }


def _render_label(label: str) -> str:
    return "{u}" if label == "¤" else label


def exact_text_runs(matches, *, space_gap: int = 3) -> list[dict]:
    """Render selected exact glyphs as style runs, preserving visible word gaps.

    Formatting changes only when glyph style changes. Spaces between glyph groups
    of the same style stay inside that style run. Printed ~ and · are emitted
    literally; the raised explanatory marker ¤ is rendered as {u}.
    """
    rows = sorted(matches, key=lambda m: (m.x, m.baseline, m.label, m.style))
    runs: list[dict] = []
    previous_right: int | None = None
    for match in rows:
        gap = previous_right is not None and match.x - previous_right - 1 >= space_gap
        label = _render_label(match.label)
        if runs and runs[-1]["style"] == match.style:
            if gap:
                runs[-1]["text"] += " "
            runs[-1]["text"] += label
        else:
            if gap:
                runs.append({"style": "space", "text": " "})
            runs.append({"style": match.style, "text": label})
        previous_right = max(previous_right or match.x1, match.x1)
    return runs


def render_exact_text(matches, *, space_gap: int = 3) -> str:
    return "".join(run["text"] for run in exact_text_runs(matches, space_gap=space_gap))


def render_exact_markup(matches, *, space_gap: int = 3) -> str:
    parts: list[str] = []
    for run in exact_text_runs(matches, space_gap=space_gap):
        text = run["text"]
        style = run["style"]
        if style == "bold":
            parts.append(f"<b>{text}</b>")
        elif style == "italic":
            parts.append(f"<i>{text}</i>")
        else:
            parts.append(text)
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Match one pixel-owned SAOL row against the exact manual glyph facit.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
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
    rows = column_entry.get("rows") or []
    if not 0 <= args.row < len(rows):
        raise SystemExit(f"row {args.row} out of range; column {args.column} has {len(rows)} rows")
    row = rows[args.row]
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=args.threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(
        row,
        column=args.column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )
    crop = page.crop(box).convert("L")
    models = load_facit(args.facit)
    result = analyse_row_exact(crop, models, threshold=args.threshold)

    print(
        f"page={args.page} column={args.column} row={args.row} "
        f"y={row['page_top']}..{row['page_bottom']} rule_x={rule_x} crop_left={box[0]} "
        f"models={len(models)} candidates={result['candidate_count']} "
        f"baseline={result['baseline']} covered={result['covered_pixels']}/{result['source_pixels']} "
        f"fully_exact={result['fully_exact']}"
    )
    if result["selected"]:
        print(f"text={render_exact_text(result['selected'])}")
        print(f"markup={render_exact_markup(result['selected'])}")
    for index, match in enumerate(result["selected"]):
        page_x = box[0] + match.x
        print(
            f"{index:02d}\tx={page_x}\tlabel={match.label!r}\tstyle={match.style}\t"
            f"baseline={box[1] + match.baseline}\tpx={match.model_pixels}\tsources={match.sources}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
