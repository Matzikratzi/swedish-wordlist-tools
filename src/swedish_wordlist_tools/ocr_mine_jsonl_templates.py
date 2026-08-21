from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _split_by_projection, _trim
from .ocr_match_jsonl import rank_articles
from .ocr_recover_tail import _known_tokens, locate_known_text
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


def _best_expected_word(ocr_word: str, expected_words: list[str]) -> tuple[str, float] | None:
    observed = _soft_word(ocr_word)
    if not observed:
        return None
    best: tuple[str, float] | None = None
    for expected in expected_words:
        exp = _soft_word(expected)
        if len(exp) != len(observed) or not exp:
            continue
        score = SequenceMatcher(None, exp, observed).ratio()
        if best is None or score > best[1]:
            best = (exp, score)
    return best


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


def _col_ink(gray: Image.Image) -> list[float]:
    return [sum((255 - gray.getpixel((x, y))) / 255.0 for y in range(gray.height)) for x in range(gray.width)]


def _boundary_quality(crop: Image.Image, spans: list[tuple[int, int]], idx: int) -> bool:
    if idx == 0 or idx == len(spans) - 1:
        return True
    proj = _col_ink(crop)
    nonzero = sorted(v for v in proj if v > 0.05)
    if not nonzero:
        return False
    median = nonzero[len(nonzero) // 2]
    threshold = max(0.8, median * 0.30)
    left, right = spans[idx]
    left_val = min(proj[max(0, left - 1)], proj[min(len(proj) - 1, left)])
    right_cut = min(len(proj) - 1, right)
    right_val = min(proj[max(0, right_cut - 1)], proj[right_cut])
    return left_val <= threshold and right_val <= threshold


def _expected_words_for_style(entry: dict[str, object], style: str) -> list[str]:
    if style == "italic":
        return _known_tokens(entry)
    # Bold and roman mining are deliberately conservative: use structural
    # headword spellings as known labels. Roman body text needs a separate
    # source of ground truth, so for now roman means non-italic headword
    # material rather than guessing labels from definitions.
    values: list[str] = []
    for key in ("stycke", "ord", "normaliserat_ord"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            cleaned = normalize_text_for_match(value)
            if cleaned:
                values.extend(cleaned.split())
    return values


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
    matched_entries = rejected_fuzzy_words = rejected_interior = rejected_boundary = 0

    for entry in entries:
        ranked = rank_articles(entry, articles)
        if not ranked or ranked[0].headword_score < args.min_headword_score:
            continue
        best = ranked[0]
        article = next((a for a in articles if a.paragraph == best.paragraph), None)
        if article is None:
            continue
        words = _article_words(article)
        if style == "italic":
            located = locate_known_text(entry, article)
            if located is None or located[2] < 0.55:
                continue
            start, end, _ = located
            if start < 0 or end > len(words) or start >= end:
                continue
            candidate_words = words[start:end]
        else:
            # Headword styles: restrict to the beginning of the matched article.
            candidate_words = words[: min(4, len(words))]

        expected_words = _expected_words_for_style(entry, style)
        if not expected_words:
            continue
        matched_entries += 1

        for word in candidate_words:
            if word.height < 6 or word.height > 18 or word.width < 2:
                continue
            pairing = _best_expected_word(word.text, expected_words)
            if pairing is None:
                continue
            expected, pair_score = pairing
            observed = _soft_word(word.text)
            if pair_score != 1.0 or observed != expected:
                rejected_fuzzy_words += 1
                continue
            crop = _trim(page_image.crop((word.left, word.top, word.left + word.width, word.top + word.height)))
            spans = _split_by_projection(crop, len(observed))
            if len(spans) != len(observed):
                continue
            for idx, exp_ch in enumerate(expected):
                if exp_ch not in wanted_chars or counts.get(exp_ch, 0) >= args.limit_per_char:
                    continue
                is_edge = idx == 0 or idx == len(expected) - 1
                if not is_edge and not args.allow_interior:
                    rejected_interior += 1
                    continue
                if not _boundary_quality(crop, spans, idx):
                    rejected_boundary += 1
                    continue
                left, right = spans[idx]
                if right <= left:
                    continue
                glyph = _trim(crop.crop((left, 0, right, crop.height)))
                if glyph.width <= 0 or glyph.height <= 0:
                    continue
                number = counts.get(exp_ch, 0)
                position_kind = "edge" if is_edge else "interior-clean"
                filename = f"{exp_ch}-{number:03d}-sub{entry.get('subnr')}-{observed}-{idx}-{position_kind}.png".replace("/", "_")
                glyph.save(style_dir / filename)
                counts[exp_ch] = number + 1
                mined.append(MinedTemplate(style, exp_ch, observed, expected, entry.get("subnr"), article.paragraph, (word.left + left, word.top, right - left, word.height), position_kind, f"{style}/{filename}"))

    manifest = {"page": args.page, "style": style, "entries_on_page": len(entries), "matched_entries": matched_entries, "counts": dict(sorted(counts.items())), "rejected_fuzzy_words": rejected_fuzzy_words, "rejected_interior": rejected_interior, "rejected_boundary": rejected_boundary, "templates": [asdict(item) for item in mined]}
    (args.out_dir / f"manifest-{style}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(manifest, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
