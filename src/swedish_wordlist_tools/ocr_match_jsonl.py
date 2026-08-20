from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .ocr_saol_normalize import article_text_for_match, normalize_text_for_match
from .ocr_tsv_articles import OcrArticle, group_articles, read_words


@dataclass(frozen=True)
class MatchCandidate:
    paragraph: int
    score: float
    headword_score: float
    text_score: float
    article_text: str


def _compact(text: str) -> str:
    return "".join(ch for ch in normalize_text_for_match(text) if ch.isalnum())


def _headword_targets(entry: dict[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("normaliserat_ord", "stycke", "ord"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            compact = _compact(value)
            if compact and compact not in values:
                values.append(compact)
    return values


def _prefix_candidates(article_text: str, lengths: Iterable[int]) -> list[str]:
    compact = _compact(article_text)
    return [compact[:length] for length in lengths if length > 0]


def _headword_score(entry: dict[str, object], article_text: str) -> float:
    targets = _headword_targets(entry)
    if not targets:
        return 0.0

    lengths = sorted({len(target) for target in targets})
    prefixes = _prefix_candidates(article_text, lengths)
    best = 0.0
    for target in targets:
        for prefix in prefixes:
            if not prefix:
                continue
            best = max(best, SequenceMatcher(None, target, prefix).ratio())
    return best


def _known_text_score(entry: dict[str, object], article_text: str) -> float:
    value = entry.get("text")
    if not isinstance(value, str) or not value.strip():
        return 0.0

    known = normalize_text_for_match(value)
    haystack = normalize_text_for_match(article_text)
    # SAOL's source notation and OCR often disagree about the glyph used for a
    # paradigm marker (+, ~, -), so compare a marker-insensitive fallback too.
    def soften(s: str) -> str:
        return " ".join(part.lstrip("+~-–—") for part in s.split())

    if known in haystack:
        return 1.0
    soft_known = soften(known)
    soft_haystack = soften(haystack)
    if soft_known and soft_known in soft_haystack:
        return 0.95

    # The known JSONL field may be truncated. Compare it against short windows
    # from the OCR article rather than demanding a whole-article match.
    best = 0.0
    words = soft_haystack.split()
    target_words = soft_known.split()
    if target_words:
        width = len(target_words)
        for i in range(max(1, len(words) - width + 1)):
            window = " ".join(words[i : i + width])
            best = max(best, SequenceMatcher(None, soft_known, window).ratio())
    return best


def rank_articles(entry: dict[str, object], articles: Iterable[OcrArticle]) -> list[MatchCandidate]:
    ranked: list[MatchCandidate] = []
    for article in articles:
        text = article_text_for_match(article)
        headword_score = _headword_score(entry, text)
        text_score = _known_text_score(entry, text)
        # Headword identity is the strongest signal. The already-known text is
        # useful confirmation but must not dominate because it is precisely the
        # field that can be truncated or OCR'd imperfectly.
        score = 0.8 * headword_score + 0.2 * text_score
        ranked.append(
            MatchCandidate(
                paragraph=article.paragraph,
                score=score,
                headword_score=headword_score,
                text_score=text_score,
                article_text=text,
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def load_entry(jsonl: Path, subnr: int) -> dict[str, object]:
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("subnr") == subnr:
                return entry
    raise SystemExit(f"subnr {subnr} not found in {jsonl}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank OCR paragraphs for one SAOL14 JSONL entry.")
    parser.add_argument("tsv", type=Path, help="Tesseract TSV for one cropped SAOL column")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entry-json", help="One JSON object containing a SAOL14 entry")
    source.add_argument("--jsonl", type=Path, help="SAOL14 JSONL file")
    parser.add_argument("--subnr", type=int, help="Entry subnr when --jsonl is used")
    parser.add_argument("--top", type=int, default=5, help="Number of ranked candidates to emit")
    args = parser.parse_args()

    if args.entry_json:
        entry = json.loads(args.entry_json)
    else:
        if args.subnr is None:
            parser.error("--subnr is required with --jsonl")
        entry = load_entry(args.jsonl, args.subnr)

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))

    result = [candidate.__dict__ for candidate in rank_articles(entry, articles)[: args.top]]
    json.dump(result, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
