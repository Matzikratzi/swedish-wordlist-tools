from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
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
    return normalize_text_for_match(printed_text(text)).strip().replace("+", "~")


def _token_specs(text: str) -> list[tuple[str, list[str | None]]]:
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
    gray = img.convert("L")
    px = gray.load()
    return [sum(1 for y in range(gray.height) if px[x, y] < threshold) for x in range(gray.width)]


def _x_groups(profile: list[int], max_gap: int = 1) -> list[tuple[int, int]]:
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
    left, top, right, bottom = box
    x0 = max(0, left - pad)
    x1 = min(crop.width, right + pad)
    y0 = max(0, top - 1)
    y1 = min(crop.height, bottom + 1)
    expanded = crop.crop((x0, y0, x1, y1))
    groups = _x_groups(_ink_columns(expanded), max_gap=1)
    if not groups:
        return None
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
    if len(overlaps) > 1 and overlaps[1][0] >= max(2, overlaps[0][0] // 2):
        return None
    glyph = _trim(expanded.crop((a, 0, b, expanded.height)))
    if glyph.width <= 0 or glyph.height <= 0:
        return None
    return glyph, (x0 + a, y0, b - a, y1 - y0)


def _token_similarity(expected: str, observed: str) -> float:
    a = _canon(expected)
    b = _canon(observed)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _candidate_windows(words: list[object], start: int, max_words: int = 3):
    for width in range(1, max_words + 1):
        end = start + width
        if end > len(words):
            break
        yield start, end, "".join(str(w.text) for w in words[start:end])
        if width > 1:
            yield start, end, " ".join(str(w.text) for w in words[start:end])


def _ordered_token_alignment(
    specs: list[tuple[str, list[str | None]]],
    words: list[object],
    min_similarity: float = 0.72,
) -> list[tuple[tuple[str, list[str | None]], list[object], float]]:
    """Align expected tokens monotonically to one or more OCR words.

    OCR often splits punctuation or joins a short form to neighbouring marks.
    Search forward over windows of up to three OCR words. Only alignments whose
    concatenated OCR text is exactly the expected printed token are harvested;
    fuzzy windows only advance the sequence so later tokens stay in order.
    """
    result: list[tuple[tuple[str, list[str | None]], list[object], float]] = []
    cursor = 0
    for spec in specs:
        raw, _styles = spec
        best: tuple[int, int, float] | None = None
        hi = min(len(words), cursor + 18)
        for i in range(cursor, hi):
            for start, end, observed in _candidate_windows(words, i):
                score = _token_similarity(raw, observed)
                if best is None or score > best[2]:
                    best = (start, end, score)
                if score == 1.0:
                    break
            if best is not None and best[2] == 1.0:
                break
        if best is None or best[2] < min_similarity:
            continue
        start, end, score = best
        result.append((spec, words[start:end], score))
        cursor = end
    return result


def _window_crop(image: Image.Image, words: list[object]) -> tuple[Image.Image, int, int]:
    left = min(int(w.left) for w in words)
    top = min(int(w.top) for w in words)
    right = max(int(w.left + w.width) for w in words)
    bottom = max(int(w.top + w.height) for w in words)
    return image.crop((left, top, right, bottom)), left, top


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
    matched_entries = exact_tokens = fuzzy_aligned_tokens = 0
    rejected_charbox = rejected_labels = rejected_geometry = 0
    rejected_x_geometry = rejected_duplicate_source = rejected_used_word = 0
    used_source_boxes: set[tuple[int, int, int, int]] = set()
    used_word_boxes: set[tuple[int, int, int, int]] = set()

    for entry in _load_page_entries(args.jsonl, args.page):
        text = entry.get("text")
        if not isinstance(text, str) or not text:
            continue
        ranked = [r for r in rank_articles(entry, articles) if r.headword_score >= args.min_headword_score]
        if not ranked:
            continue

        article = None
        for candidate in ranked[:6]:
            maybe = next((a for a in articles if a.paragraph == candidate.paragraph), None)
            if maybe is None:
                continue
            # Do not lock an entire paragraph. Reject only candidates whose OCR
            # word geometry is already wholly consumed by earlier entries.
            candidate_boxes = {(int(w.left), int(w.top), int(w.width), int(w.height)) for w in _article_words(maybe)}
            if candidate_boxes and candidate_boxes.issubset(used_word_boxes):
                continue
            article = maybe
            break
        if article is None:
            continue
        matched_entries += 1

        specs = _token_specs(text)
        words = _article_words(article)
        for (raw, styles), aligned_words, align_score in _ordered_token_alignment(specs, words):
            if align_score < 1.0:
                fuzzy_aligned_tokens += 1
                continue
            printed = printed_text(normalize_text_for_match(raw).strip()).replace("+", "~")
            observed_joined = "".join(normalize_text_for_match(w.text).strip() for w in aligned_words).replace("+", "~")
            observed_spaced = " ".join(normalize_text_for_match(w.text).strip() for w in aligned_words).replace("+", "~")
            if printed not in {observed_joined, observed_spaced} or len(printed) != len(styles):
                continue
            exact_tokens += 1

            word_boxes = {(int(w.left), int(w.top), int(w.width), int(w.height)) for w in aligned_words}
            if word_boxes and word_boxes.issubset(used_word_boxes):
                rejected_used_word += 1
                continue

            crop, crop_left, crop_top = _window_crop(image, aligned_words)
            if crop.width < 2 or crop.height < 6 or crop.height > 20:
                rejected_geometry += 1
                continue
            boxes = _tesseract_char_boxes(crop, len(printed))
            if boxes is None:
                rejected_charbox += 1
                continue
            if not _labels_match(boxes, printed):
                rejected_labels += 1
                continue

            harvested_any = False
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
                source_bbox = (crop_left + gl, crop_top + gt, gw, gh)
                if source_bbox in used_source_boxes:
                    rejected_duplicate_source += 1
                    continue
                used_source_boxes.add(source_bbox)

                label = _safe_character_name(ch)
                safe_word = "".join(c if c.isalnum() else "_" for c in printed)
                filename = f"{label}-{n:03d}-sub{entry.get('subnr')}-{safe_word}-{idx}-xclean.png"
                glyph.save(args.out_dir / style / filename)
                counts[style][ch] = n + 1
                harvested_any = True
                mined.append(TypographicTemplate(
                    style=style,
                    character=ch,
                    source_word=" ".join(str(w.text) for w in aligned_words),
                    expected_word=printed,
                    subnr=entry.get("subnr"),
                    paragraph=article.paragraph,
                    bbox=source_bbox,
                    position_kind="ordered-window-xclean",
                    output=f"{style}/{filename}",
                ))
            if harvested_any:
                used_word_boxes.update(word_boxes)

    result = {
        "page": args.page,
        "counts": {s: dict(sorted(v.items())) for s, v in counts.items()},
        "matched_entries": matched_entries,
        "exact_tokens": exact_tokens,
        "fuzzy_aligned_tokens": fuzzy_aligned_tokens,
        "rejected_charbox_count": rejected_charbox,
        "rejected_charbox_labels": rejected_labels,
        "rejected_geometry": rejected_geometry,
        "rejected_x_geometry": rejected_x_geometry,
        "rejected_duplicate_source": rejected_duplicate_source,
        "rejected_used_word": rejected_used_word,
        "templates": [asdict(x) for x in mined],
        "notes": {
            "plus_printed_as": "~",
            "square_brackets": "excluded",
            "glyph_crop": "Tesseract box expanded then reduced to one horizontal ink group",
            "source_bbox_reuse": "rejected",
            "paragraph_reuse": "allowed; only already-consumed OCR word geometry is rejected",
            "token_alignment": "expected tokens aligned monotonically to 1-3 OCR-word windows; only exact windows harvested",
        },
    }
    (args.out_dir / "manifest-typographic.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    json.dump(result, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
