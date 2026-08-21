from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _split_by_projection, _trim
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
    """Use only exact labels that are unlikely to occur by chance elsewhere.

    OCR paragraph grouping can merge several printed articles.  Generic form
    tokens such as n, s., pl. and el. are therefore unsafe labels even when
    they match JSONL exactly.  Three or more alphanumeric characters give us
    a conservative source of glyph ground truth.
    """
    return sum(ch.isalnum() for ch in token) >= 3


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

        # For italic form text, do not use locate_known_text(): that routine is
        # intentionally fuzzy because it serves truncation recovery.  Glyph
        # mining needs the opposite property: exact labels.  Scan the matched
        # OCR article and accept only exact, informative JSONL tokens.
        if style == "italic":
            expected_exact = {_soft_word(token) for token in expected_words}
            expected_exact.discard("")
            candidate_words = _article_words(article)
        else:
            expected_exact = {_soft_word(token) for token in expected_words}
            expected_exact.discard("")
            candidate_words = _article_words(article)[:4]

        for word in candidate_words:
            if word.height < 6 or word.height > 18 or word.width < 2:
                rejected_geometry += 1
                continue
            observed = _soft_word(word.text)
            if not observed:
                continue
            if observed not in expected_exact:
                continue
            if style == "italic" and not _informative_exact_token(observed):
                rejected_uninformative += 1
                continue

            expected = observed
            exact_word_matches += 1
            crop = _trim(page_image.crop((word.left, word.top, word.left + word.width, word.top + word.height)))
            spans = _split_by_projection(crop, len(observed))
            if len(spans) != len(observed):
                rejected_split += 1
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
                    rejected_geometry += 1
                    continue
                glyph = _trim(crop.crop((left, 0, right, crop.height)))
                if glyph.width <= 0 or glyph.height <= 0:
                    rejected_geometry += 1
                    continue
                number = counts.get(exp_ch, 0)
                position_kind = "edge" if is_edge else "interior-clean"
                label = _safe_character_name(exp_ch)
                safe_observed = "".join(ch if ch.isalnum() else "_" for ch in observed)
                filename = f"{label}-{number:03d}-sub{entry.get('subnr')}-{safe_observed}-{idx}-{position_kind}.png"
                glyph.save(style_dir / filename)
                counts[exp_ch] = number + 1
                mined.append(MinedTemplate(style, exp_ch, observed, expected, entry.get("subnr"), article.paragraph, (word.left + left, word.top, right - left, word.height), position_kind, f"{style}/{filename}"))

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
