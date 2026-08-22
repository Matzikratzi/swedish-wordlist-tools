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


def _ink_columns(img: Image.Image, threshold: int = 220) -> list[int]:
    """Count dark pixels in each x column of a grayscale crop."""
    gray = img.convert("L")
    px = gray.load()
    return [sum(1 for y in range(gray.height) if px[x, y] < threshold) for x in range(gray.width)]


def _x_groups(profile: list[int], max_gap: int = 1) -> list[tuple[int, int]]:
    """Return horizontal ink groups, bridging at most max_gap empty columns.

    This deliberately works in x only: dots over i/ä and the two dots in ':'
    remain part of the same glyph group because their x ranges overlap.
    """
    active = [i for i, n in enumerate(profile) if n > 0]
    if not active:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = active[0]
    for x in active[1:]:
        if x - prev > max_gap + 1:
            groups.append((start, prev + 1))
            start = x
        prev = x
    groups.append((start, prev + 1))
    return groups


def _sanitize_charbox(crop: Image.Image, box: tuple[int, int, int, int], pad: int = 3) -> tuple[Image.Image, tuple[int, int, int, int]] | None:
    """Trim a Tesseract charbox to one horizontal glyph group.

    The charbox is expanded slightly so accidental neighbor capture is visible.
    We then inspect horizontal ink groups. A valid glyph should occupy one group
    in x (possibly made from several vertical components such as i, ä or ':').
    If multiple groups overlap the proposed character region ambiguously, reject
    the sample instead of poisoning the template library.
    """
    left, top, right, bottom = box
    x0 = max(0, left - pad)
    x1 = min(crop.width, right + pad)
    y0 = max(0, top - 1)
    y1 = min(crop.height, bottom + 1)
    expanded = crop.crop((x0, y0, x1, y1))
    profile = _ink_columns(expanded)
    groups = _x_groups(profile, max_gap=1)
    if not groups:
        return None

    # Expected charbox position in expanded-crop coordinates.
    expected_l = left - x0
    expected_r = right - x0
    overlaps: list[tuple[int, int, int]] = []
    for a, b in groups:
        overlap = max(0, min(b, expected_r) - max(a, expected_l))
        if overlap:
            overlaps.append((overlap, a, b))
    if not overlaps:
        return None
    overlaps.sort(reverse=True)
    _ov, a, b = overlaps[0]
    # If two separated groups substantially overlap the expected box, the crop
    # is ambiguous (often two letters fused into one OCR box): reject it.
    if len(overlaps) > 1 and overlaps[1][0] >= max(2, overlaps[0][0] // 2):
        return None

    # Keep only the chosen x-group. Vertical trimming happens afterward in _trim.
    glyph = _trim(expanded.crop((a, 0, b, expanded.height)))
    if glyph.width <= 0 or glyph.height <= 0:
        return None
    final_left = x0 + a
    final_top = y0
    return glyph, (final_left, final_top, b - a, y1 - y0)


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
    rejected_x_geometry = rejected_duplicate_source = 0
    used_source_boxes: set[tuple[int, int, int, int]] = set()

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

        used_token_candidates: dict[str, int] = {}
        for word in _article_words(article):
            if word.height < 6 or word.height > 18 or word.width < 2:
                rejected_geometry += 1
                continue
            key = _canon(word.text)
            candidates = expected.get(key, [])
            if not candidates:
                continue
            candidate_index = used_token_candidates.get(key, 0)
            if candidate_index >= len(candidates):
                continue
            raw, styles = candidates[candidate_index]
            used_token_candidates[key] = candidate_index + 1
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
                sanitized = _sanitize_charbox(crop, (left, top, right, bottom))
                if sanitized is None:
                    rejected_x_geometry += 1
                    continue
                glyph, local_bbox = sanitized
                gl, gt, gw, gh = local_bbox
                source_bbox = (word.left + gl, word.top + gt, gw, gh)
                if source_bbox in used_source_boxes:
                    rejected_duplicate_source += 1
                    continue
                used_source_boxes.add(source_bbox)

                label = _safe_character_name(ch)
                safe_word = "".join(c if c.isalnum() else "_" for c in printed)
                filename = f"{label}-{n:03d}-sub{entry.get('subnr')}-{safe_word}-{idx}-xclean.png"
                glyph.save(args.out_dir / style / filename)
                counts[style][ch] = n + 1
                mined.append(TypographicTemplate(
                    style=style,
                    character=ch,
                    source_word=word.text,
                    expected_word=printed,
                    subnr=entry.get("subnr"),
                    paragraph=article.paragraph,
                    bbox=source_bbox,
                    position_kind="mixed-style-xclean",
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
        "rejected_x_geometry": rejected_x_geometry,
        "rejected_duplicate_source": rejected_duplicate_source,
        "templates": [asdict(x) for x in mined],
        "notes": {
            "plus_printed_as": "~",
            "square_brackets": "excluded",
            "glyph_crop": "Tesseract box expanded then reduced to one horizontal ink group",
            "source_bbox_reuse": "rejected",
        },
    }
    (args.out_dir / "manifest-typographic.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    json.dump(result, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
