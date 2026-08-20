from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _split_by_projection, _trim
from .ocr_match_jsonl import rank_articles
from .ocr_recover_tail import _known_tokens, _raw_tokens, locate_known_text
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
        # Exact character alignment is needed before we label individual glyphs.
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine real italic SAOL glyph templates from JSONL-known inflection text aligned to OCR."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("image", type=Path, help="One cropped SAOL column image")
    parser.add_argument("tsv", type=Path, help="Tesseract TSV for that same column")
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-headword-score", type=float, default=0.72)
    parser.add_argument("--min-word-score", type=float, default=0.86)
    parser.add_argument("--limit-per-char", type=int, default=12)
    args = parser.parse_args()

    style = "italic"
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

    for entry in entries:
        ranked = rank_articles(entry, articles)
        if not ranked or ranked[0].headword_score < args.min_headword_score:
            continue
        best = ranked[0]
        article = next((a for a in articles if a.paragraph == best.paragraph), None)
        if article is None:
            continue
        located = locate_known_text(entry, article)
        if located is None or located[2] < 0.55:
            continue

        start, end, _ = located
        words = _article_words(article)
        if start < 0 or end > len(words) or start >= end:
            continue
        expected_words = _known_tokens(entry)
        if not expected_words:
            continue
        matched_entries += 1

        for word in words[start:end]:
            # Merged/tall OCR boxes are dangerous for character extraction.
            if word.height < 6 or word.height > 18 or word.width < 2:
                continue
            pairing = _best_expected_word(word.text, expected_words)
            if pairing is None:
                continue
            expected, pair_score = pairing
            if pair_score < args.min_word_score:
                continue
            observed = _soft_word(word.text)
            if len(expected) != len(observed):
                continue

            crop = _trim(page_image.crop((word.left, word.top, word.left + word.width, word.top + word.height)))
            spans = _split_by_projection(crop, len(observed))
            if len(spans) != len(observed):
                continue

            for idx, (obs_ch, exp_ch) in enumerate(zip(observed, expected)):
                # Only mine characters for which OCR and JSONL already agree.
                # Ambiguous/disagreeing positions are exactly what these templates
                # will later be used to adjudicate.
                if obs_ch != exp_ch or exp_ch not in wanted_chars:
                    continue
                if counts.get(exp_ch, 0) >= args.limit_per_char:
                    continue
                left, right = spans[idx]
                if right <= left:
                    continue
                glyph = _trim(crop.crop((left, 0, right, crop.height)))
                if glyph.width <= 0 or glyph.height <= 0:
                    continue
                number = counts.get(exp_ch, 0)
                filename = f"{exp_ch}-{number:03d}-sub{entry.get('subnr')}-{observed}-{idx}.png".replace("/", "_")
                glyph.save(style_dir / filename)
                counts[exp_ch] = number + 1
                mined.append(
                    MinedTemplate(
                        style=style,
                        character=exp_ch,
                        source_word=observed,
                        expected_word=expected,
                        subnr=entry.get("subnr"),
                        paragraph=article.paragraph,
                        bbox=(word.left + left, word.top, right - left, word.height),
                        output=f"{style}/{filename}",
                    )
                )

    manifest = {
        "page": args.page,
        "style": style,
        "entries_on_page": len(entries),
        "matched_entries": matched_entries,
        "counts": dict(sorted(counts.items())),
        "templates": [asdict(item) for item in mined],
    }
    (args.out_dir / "manifest-italic.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    json.dump(manifest, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
