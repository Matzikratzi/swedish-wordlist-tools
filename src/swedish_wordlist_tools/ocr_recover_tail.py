from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .ocr_match_jsonl import load_entry, rank_articles
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import OcrArticle, group_articles, read_words


_MARKER_PREFIX = "+~-–—"
_STOP_PREFIXES = ("•", "♦", "◆", "◊", "«", "»")


@dataclass(frozen=True)
class TailRecovery:
    paragraph: int
    article_score: float
    headword_score: float
    known_text_score: float
    known_text: str
    recovered_tail: str
    stop_reason: str
    raw_article_lines: tuple[str, ...]


def _soft_token(text: str) -> str:
    return normalize_text_for_match(text).strip().lstrip(_MARKER_PREFIX)


def _raw_tokens(article: OcrArticle) -> list[str]:
    return [word.text for line in article.lines for word in line.words]


def _raw_lines(article: OcrArticle) -> tuple[str, ...]:
    return tuple(" ".join(word.text for word in line.words) for line in article.lines)


def _known_tokens(entry: dict[str, object]) -> list[str]:
    text = entry.get("text")
    if not isinstance(text, str):
        return []
    return [token for token in (_soft_token(part) for part in text.split()) if token]


def _window_score(target: list[str], candidate: list[str]) -> float:
    if not target or not candidate:
        return 0.0
    return SequenceMatcher(None, " ".join(target), " ".join(candidate)).ratio()


def locate_known_text(entry: dict[str, object], article: OcrArticle) -> tuple[int, int, float] | None:
    target = _known_tokens(entry)
    if not target:
        return None

    raw = _raw_tokens(article)
    soft = [_soft_token(token) for token in raw]
    best: tuple[int, int, float] | None = None
    for width in range(max(1, len(target) - 1), len(target) + 2):
        for start in range(0, max(0, len(soft) - width + 1)):
            end = start + width
            score = _window_score(target, [token for token in soft[start:end] if token])
            if best is None or score > best[2]:
                best = (start, end, score)
    return best


def _is_stop_token(token: str) -> str | None:
    stripped = token.strip()
    if not stripped:
        return None
    if stripped.startswith(_STOP_PREFIXES):
        return "bullet"
    if re.fullmatch(r"\d+[.)]?", stripped):
        return "sense-number"
    return None


def _line_token_ranges(article: OcrArticle) -> list[tuple[int, int, object]]:
    ranges = []
    offset = 0
    for line in article.lines:
        start = offset
        offset += len(line.words)
        ranges.append((start, offset, line))
    return ranges


def _looks_like_new_headword_line(line) -> bool:
    """Conservative signal that a visual line starts a new SAOL article.

    We intentionally avoid linguistic guessing.  SAOL headword lines normally
    start near the left article margin, have a word-like first token, and then
    quickly contain pronunciation/word-class material.  This catches the giant
    Tesseract-paragraph failure without treating wrapped definition lines as
    new articles.
    """
    if not line.words:
        return False
    first = line.words[0]
    token = normalize_text_for_match(first.text).strip()
    if not token or len(token) < 2:
        return False
    if not any(ch.isalpha() for ch in token):
        return False
    # Wrapped prose often starts indented; real headwords in a cropped column
    # are generally at the column's left text margin. Empirically allow a broad
    # margin because Tesseract geometry is noisy.
    if first.left > 80:
        return False
    text = " ".join(word.text for word in line.words[:5])
    norm = normalize_text_for_match(text)
    # Strong structural cues appearing shortly after the first token.
    cues = (" s.", " s ", " adj.", " adj ", " v.", " v ", " adv.", " prep.", " pron.", " n ", "[-", "[")
    return any(cue in f" {norm} " for cue in cues)


def _next_article_token(article: OcrArticle, after_token: int) -> int | None:
    ranges = _line_token_ranges(article)
    # Never stop on the same visual line as the known truncation point. Start
    # looking at subsequent lines only.
    current_line_idx = None
    for idx, (start, end, _line) in enumerate(ranges):
        if start <= max(0, after_token - 1) < end:
            current_line_idx = idx
            break
    if current_line_idx is None:
        return None
    for start, _end, line in ranges[current_line_idx + 1 :]:
        if _looks_like_new_headword_line(line):
            return start
    return None


def recover_tail(
    entry: dict[str, object],
    article: OcrArticle,
    article_score: float = 0.0,
    headword_score: float = 0.0,
) -> TailRecovery:
    located = locate_known_text(entry, article)
    known_text = str(entry.get("text") or "")
    if located is None:
        return TailRecovery(article.paragraph, article_score, headword_score, 0.0, known_text, "", "known-text-not-found", _raw_lines(article))

    _start, end, score = located
    raw = _raw_tokens(article)
    next_article = _next_article_token(article, end)
    tail: list[str] = []
    stop_reason = "article-end"
    for pos, token in enumerate(raw[end:], start=end):
        if next_article is not None and pos >= next_article:
            stop_reason = "next-headword-line"
            break
        reason = _is_stop_token(token)
        if reason:
            stop_reason = reason
            break
        tail.append(token)

    return TailRecovery(
        paragraph=article.paragraph,
        article_score=round(article_score, 4),
        headword_score=round(headword_score, 4),
        known_text_score=round(score, 4),
        known_text=known_text,
        recovered_tail=" ".join(tail).strip(),
        stop_reason=stop_reason,
        raw_article_lines=_raw_lines(article),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservatively recover text after a known SAOL14 JSONL text prefix.")
    parser.add_argument("tsv", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entry-json")
    source.add_argument("--jsonl", type=Path)
    parser.add_argument("--subnr", type=int)
    args = parser.parse_args()

    if args.entry_json:
        entry = json.loads(args.entry_json)
    else:
        if args.subnr is None:
            parser.error("--subnr is required with --jsonl")
        entry = load_entry(args.jsonl, args.subnr)

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))

    ranked = rank_articles(entry, articles)
    if not ranked:
        raise SystemExit("no OCR articles found")
    best = ranked[0]
    article = next(a for a in articles if a.paragraph == best.paragraph)
    result = recover_tail(entry, article, best.score, best.headword_score)
    json.dump(asdict(result), __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
