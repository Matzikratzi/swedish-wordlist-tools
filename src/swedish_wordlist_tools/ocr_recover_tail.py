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
    tail: list[str] = []
    stop_reason = "article-end"
    for token in raw[end:]:
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
