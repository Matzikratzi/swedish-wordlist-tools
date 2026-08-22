from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _trim
from .ocr_match_jsonl import rank_articles
from .ocr_mine_jsonl_templates import (
    _article_words,
    _canonical_printed_char,
    _load_page_entries,
    _safe_character_name,
    _tesseract_char_boxes,
)
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_typography_segments import classify_inflection_text, printed_text


@dataclass(frozen=True)
class TypographicTemplate:
    style: str
    character: str
    source_word: str
    expected_word: str
    subnr: object
    paragraph: int
    bbox: tuple[int, int, int, int]
    position_kind: str
    output: str


def _canon(text: str) -> str:
    return normalize_text_for_match(printed_text(text)).strip()


def _token_specs(text: str) -> list[tuple[str, list[str | None]]]:
    """Return whitespace tokens with a per-character style mask.

    Characters inside [...] have style None and are never harvested. The token
    itself is retained so OCR alignment is not shifted by omitted pronunciation
    material.
    """
    mask: list[str | None] = [None] * len(text)
    for seg in classify_inflection_text(text):
        for i in range(seg.start, seg.end):
            if 0 <= i < len(mask):
                mask[i] = seg.style
    out: list[tuple[str, list[str | None]]] = []
    for m in re.finditer(r"\S+", text):
        out.append((m.group(0), mask[m.start():m.end()]))
    return out


def _labels_match(boxes: list[tuple[str, int, int, int, int]], printed: str) -> bool:
    if len(boxes) != len(printed):
        return False
    return all(_canonical_printed_char(got) == _canonical_printed_char(exp)
               for (got, *_), exp in zip(boxes, printed))


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine all safe SAOL glyphs outside [] with per-character typography.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("image", type=Path)
    ap.add_argument("tsv", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--limit-per-char", type=int, default=30)
    ap.add_argument("--min-headword-score", type=float, default=0.72)
    args = ap.parse_args()

    image = Image.open(args.image).convert("L")
    from .ocr_tsv_articles import group_articles, read_words
    with args.tsv.open("r", encoding="utf-8", newline="") as f:
        articles = group_articles(read_words(f))

    for style in ("italic", "roman"):
        (args.out_dir / style).mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {"italic": {}, "roman": {}}
    mined: list[TypographicTemplate] = []
    matched_entries = exact_tokens = 0
    rejected_charbox = rejected_labels = rejected_geometry = 0

    for entry in _load_page_entries(args.jsonl, args.page):
        text = entry.get("text")
        if not isinstance(text, str) or not text:
            continue
        ranked = rank_articles(entry, articles)
        if not ranked or ranked[0].headword_score < args.min_headword_score:
            continue
        article = next((a for a in articles if a.paragraph == ranked[0].paragraph), None)
        if article is None:
            continue
        matched_entries += 1

        expected: dict[str, list[tuple[str, list[str | None]]]] = {}
        for raw, styles in _token_specs(text):
            key = _canon(raw)
            if key:
                expected.setdefault(key, []).append((raw, styles))

        for word in _article_words(article):
            if word.height < 6 or word.height > 18 or word.width < 2:
                rejected_geometry += 1
                continue
            key = _canon(word.text)
            candidates = expected.get(key, [])
            if not candidates:
                continue
            raw, styles = candidates[0]
            printed = printed_text(normalize_text_for_match(raw).strip())
            observed = normalize_text_for_match(word.text).strip().replace("+", "~")
            if printed != observed or len(printed) != len(styles):
                continue
            exact_tokens += 1
            crop = image.crop((word.left, word.top, word.left + word.width, word.top + word.height))
            boxes = _tesseract_char_boxes(crop, len(printed))
            if boxes is None:
                rejected_charbox += 1
                continue
            if not _labels_match(boxes, printed):
                rejected_labels += 1
                continue

            for idx, (ch, style) in enumerate(zip(printed, styles)):
                if style not in {"italic", "roman"}:
                    continue
                n = counts[style].get(ch, 0)
                if n >= args.limit_per_char:
                    continue
                _ocr, left, top, right, bottom = boxes[idx]
                glyph = _trim(crop.crop((left, top, right, bottom)))
                if glyph.width <= 0 or glyph.height <= 0:
                    continue
                label = _safe_character_name(ch)
                safe_word = "".join(c if c.isalnum() else "_" for c in printed)
                filename = f"{label}-{n:03d}-sub{entry.get('subnr')}-{safe_word}-{idx}-charbox.png"
                glyph.save(args.out_dir / style / filename)
                counts[style][ch] = n + 1
                mined.append(TypographicTemplate(
                    style=style,
                    character=ch,
                    source_word=word.text,
                    expected_word=printed,
                    subnr=entry.get("subnr"),
                    paragraph=article.paragraph,
                    bbox=(word.left + left, word.top + top, right-left, bottom-top),
                    position_kind="mixed-style-charbox",
                    output=f"{style}/{filename}",
                ))

    result = {
        "page": args.page,
        "counts": {s: dict(sorted(v.items())) for s, v in counts.items()},
        "matched_entries": matched_entries,
        "exact_tokens": exact_tokens,
        "rejected_charbox_count": rejected_charbox,
        "rejected_charbox_labels": rejected_labels,
        "rejected_geometry": rejected_geometry,
        "templates": [asdict(x) for x in mined],
        "notes": {"plus_printed_as": "~", "square_brackets": "excluded"},
    }
    (args.out_dir / "manifest-typographic.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    json.dump(result, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
