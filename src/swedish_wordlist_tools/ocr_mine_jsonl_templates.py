from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _trim
from .ocr_match_jsonl import rank_articles
from .ocr_recover_tail import _known_tokens
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import OcrArticle, OcrWord, group_articles, read_words


@dataclass(frozen=True)
class MinedTemplate:
    style: str
    character: str
    source_word: str
    expected_word: str
    subnr: object
    paragraph: int
    bbox: tuple[int, int, int, int]
    position_kind: str
    output: str


def _soft_word(text: str) -> str:
    return normalize_text_for_match(text).strip().lstrip("+~-–—")


def _article_words(article: OcrArticle) -> list[OcrWord]:
    return [word for line in article.lines for word in line.words]


def _load_page_entries(jsonl: Path, page: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("sidnr1") == page and isinstance(entry.get("text"), str) and entry.get("text"):
                result.append(entry)
    return result


def _expected_words_for_style(entry: dict[str, object], style: str) -> list[str]:
    if style == "italic":
        return _known_tokens(entry)
    values: list[str] = []
    for key in ("stycke", "ord", "normaliserat_ord"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            cleaned = normalize_text_for_match(value)
            if cleaned:
                values.extend(cleaned.split())
    return values


def _safe_character_name(ch: str) -> str:
    if ch.isalnum():
        return ch
    return f"u{ord(ch):04x}"


def _informative_exact_token(token: str) -> bool:
    return sum(ch.isalnum() for ch in token) >= 3


def _printed_form(jsonl_token: str, ocr_token: str) -> tuple[str, str] | None:
    labels = normalize_text_for_match(jsonl_token).strip()
    observed = normalize_text_for_match(ocr_token).strip()
    if not labels or not observed:
        return None
    printed = labels.replace("+", "~")
    canonical_expected = printed.replace("+", "~")
    canonical_observed = observed.replace("+", "~")
    if canonical_expected != canonical_observed:
        return None
    if len(labels) != len(observed):
        return None
    return labels, printed


def _canonical_printed_char(ch: str) -> str:
    if ch in {"+", "~"}:
        return "~"
    return normalize_text_for_match(ch).strip()


def _charbox_labels_match(
    boxes: list[tuple[str, int, int, int, int]], printed: str
) -> bool:
    if len(boxes) != len(printed):
        return False
    for (ocr_ch, *_coords), expected_ch in zip(boxes, printed):
        if _canonical_printed_char(ocr_ch) != _canonical_printed_char(expected_ch):
            return False
    return True


def _tesseract_char_boxes(crop: Image.Image, expected_len: int) -> list[tuple[str, int, int, int, int]] | None:
    if expected_len <= 0:
        return None
    with tempfile.TemporaryDirectory(prefix="saol-charbox-") as tmp:
        image_path = Path(tmp) / "word.png"
        crop.save(image_path)
        proc = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", "swe", "--psm", "8", "makebox"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            return None
        boxes: list[tuple[str, int, int, int, int]] = []
        h = crop.height
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                ch = parts[0]
                left, bottom, right, top = map(int, parts[1:5])
            except ValueError:
                continue
            x0 = max(0, left)
            x1 = min(crop.width, right)
            y0 = max(0, h - top)
            y1 = min(crop.height, h - bottom)
            if x1 <= x0 or y1 <= y0:
                continue
            boxes.append((ch, x0, y0, x1, y1))
        boxes.sort(key=lambda item: (item[1], item[2]))
        return boxes if len(boxes) == expected_len else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine conservative real SAOL glyph templates from JSONL-known text aligned to OCR.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--style", choices=("italic", "bold", "roman"), default="italic")
    parser.add_argument("--min-headword-score", type=float, default=0.72)
    parser.add_argument("--limit-per-char", type=int, default=12)
    parser.add_argument("--allow-interior", action="store_true")
    parser.add_argument("--bold-all-chars", action="store_true")
    parser.add_argument("--debug-pairs", type=int, default=12)
    args = parser.parse_args()

    style = args.style
    style_dir = args.out_dir / style
    style_dir.mkdir(parents=True, exist_ok=True)
    wanted_chars = set(args.chars)
    page_image = Image.open(args.image).convert("L")
    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))

    entries = _load_page_entries(args.jsonl, args.page)
    counts: dict[str, int] = {}
    mined: list[MinedTemplate] = []
    matched_entries = 0
    exact_word_matches = 0
    rejected_fuzzy_words = 0
    rejected_interior = 0
    rejected_boundary = 0
    rejected_split = 0
    rejected_geometry = 0
    rejected_uninformative = 0
    rejected_charbox_count = 0
    rejected_charbox_labels = 0
    fuzzy_examples: list[dict[str, object]] = []

    for entry in entries:
        ranked = rank_articles(entry, articles)
        if not ranked or ranked[0].headword_score < args.min_headword_score:
            continue
        best = ranked[0]
        article = next((a for a in articles if a.paragraph == best.paragraph), None)
        if article is None:
            continue

        expected_words = _expected_words_for_style(entry, style)
        if not expected_words:
            continue
        matched_entries += 1

        expected_by_soft: dict[str, list[str]] = {}
        for token in expected_words:
            soft = _soft_word(token)
            if soft:
                expected_by_soft.setdefault(soft, []).append(token)

        article_words = _article_words(article)
        if style == "italic":
            candidate_words = article_words
        elif style == "bold":
            candidate_words = article_words[:1]
        else:
            candidate_words = article_words[:4]

        for word in candidate_words:
            if word.height < 6 or word.height > 18 or word.width < 2:
                rejected_geometry += 1
                continue
            observed_soft = _soft_word(word.text)
            raw_candidates = expected_by_soft.get(observed_soft, [])
            if not raw_candidates:
                continue

            pair = None
            for raw_expected in raw_candidates:
                candidate = _printed_form(raw_expected, word.text)
                if candidate is not None:
                    pair = candidate
                    break
            if pair is None:
                rejected_fuzzy_words += 1
                continue
            labels, printed = pair
            if style == "italic" and not _informative_exact_token(labels):
                rejected_uninformative += 1
                continue

            exact_word_matches += 1
            word_crop = page_image.crop((word.left, word.top, word.left + word.width, word.top + word.height))
            boxes = _tesseract_char_boxes(word_crop, len(labels))
            if boxes is None:
                rejected_charbox_count += 1
                continue
            if not _charbox_labels_match(boxes, printed):
                rejected_charbox_labels += 1
                continue

            for idx, exp_ch in enumerate(labels):
                if style == "bold" and not args.bold_all_chars and idx != 0:
                    continue
                if exp_ch not in wanted_chars or counts.get(exp_ch, 0) >= args.limit_per_char:
                    continue
                is_edge = idx == 0 or idx == len(labels) - 1
                if style != "bold" and not is_edge and not args.allow_interior:
                    rejected_interior += 1
                    continue
                _ocr_ch, left, top, right, bottom = boxes[idx]
                glyph = _trim(word_crop.crop((left, top, right, bottom)))
                if glyph.width <= 0 or glyph.height <= 0:
                    rejected_geometry += 1
                    continue
                number = counts.get(exp_ch, 0)
                if style == "bold":
                    position_kind = "initial" if idx == 0 else "headword-interior"
                else:
                    position_kind = "edge" if is_edge else "interior-charbox"
                label = _safe_character_name(exp_ch)
                safe_observed = "".join(ch if ch.isalnum() else "_" for ch in printed)
                filename = f"{label}-{number:03d}-sub{entry.get('subnr')}-{safe_observed}-{idx}-{position_kind}.png"
                glyph.save(style_dir / filename)
                counts[exp_ch] = number + 1
                mined.append(
                    MinedTemplate(
                        style,
                        exp_ch,
                        word.text,
                        labels,
                        entry.get("subnr"),
                        article.paragraph,
                        (word.left + left, word.top + top, right - left, bottom - top),
                        position_kind,
                        f"{style}/{filename}",
                    )
                )

    manifest = {
        "page": args.page,
        "style": style,
        "entries_on_page": len(entries),
        "matched_entries": matched_entries,
        "exact_word_matches": exact_word_matches,
        "counts": dict(sorted(counts.items())),
        "rejected_fuzzy_words": rejected_fuzzy_words,
        "rejected_uninformative": rejected_uninformative,
        "rejected_interior": rejected_interior,
        "rejected_boundary": rejected_boundary,
        "rejected_split": rejected_split,
        "rejected_charbox_count": rejected_charbox_count,
        "rejected_charbox_labels": rejected_charbox_labels,
        "rejected_geometry": rejected_geometry,
        "fuzzy_examples": fuzzy_examples,
        "templates": [asdict(item) for item in mined],
    }
    (args.out_dir / f"manifest-{style}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(manifest, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
