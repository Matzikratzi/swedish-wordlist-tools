from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .ocr_match_jsonl import load_entry, rank_articles
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import OcrArticle, OcrLine, group_articles, read_words

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


def _line_tokens(line: OcrLine) -> list[str]:
    return [word.text for word in line.words]


def locate_known_text(entry: dict[str, object], article: OcrArticle) -> tuple[int, int, int, float] | None:
    """Locate the JSONL-known text in visual line coordinates.

    Returns (line_index, start_word, end_word, score). The search may span at
    most two adjacent visual lines; it never flattens an entire Tesseract
    paragraph, which avoids accidental traversal across unrelated articles.
    """
    target = _known_tokens(entry)
    if not target:
        return None
    best = None
    for line_idx, line in enumerate(article.lines):
        combined = list(line.words)
        next_count = 0
        if line_idx + 1 < len(article.lines):
            next_count = len(article.lines[line_idx + 1].words)
            combined += list(article.lines[line_idx + 1].words)
        soft = [_soft_token(w.text) for w in combined]
        for width in range(max(1, len(target) - 1), len(target) + 2):
            for start in range(0, max(0, len(soft) - width + 1)):
                end = start + width
                score = _window_score(target, [t for t in soft[start:end] if t])
                if best is None or score > best[3]:
                    best = (line_idx, start, end, score)
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


def _looks_like_new_headword_line(line: OcrLine) -> bool:
    if not line.words:
        return False
    first = line.words[0]
    token = normalize_text_for_match(first.text).strip()
    if len(token) < 2 or not any(ch.isalpha() for ch in token):
        return False
    if first.left > 82:
        return False
    norm = normalize_text_for_match(" ".join(w.text for w in line.words[:6]))
    cues = (" s.", " s ", " adj.", " adj ", " v.", " v ", " adv.", " prep.", " pron.", "[-", "[")
    return any(cue in f" {norm} " for cue in cues)


def _suffix_from_last_word(known_last: str, ocr_last: str) -> str:
    known = _soft_token(known_last)
    observed = _soft_token(ocr_last)
    if not known or not observed:
        return ""
    if observed.startswith(known):
        return observed[len(known):]
    best_split = None
    best_score = 0.0
    lo = max(1, len(known) - 2)
    hi = min(len(observed), len(known) + 3)
    for split in range(lo, hi + 1):
        score = SequenceMatcher(None, known, observed[:split]).ratio()
        if score > best_score:
            best_score = score
            best_split = split
    if best_split is not None and best_score >= 0.72 and best_split < len(observed):
        return observed[best_split:]
    return ""


def recover_tail(entry: dict[str, object], article: OcrArticle, article_score: float = 0.0, headword_score: float = 0.0) -> TailRecovery:
    located = locate_known_text(entry, article)
    known_text = str(entry.get("text") or "")
    if located is None:
        return TailRecovery(article.paragraph, article_score, headword_score, 0.0, known_text, "", "known-text-not-found", _raw_lines(article))

    line_idx, start, end, score = located
    first_line = article.lines[line_idx]
    second_line = article.lines[line_idx + 1] if line_idx + 1 < len(article.lines) else None
    combined = list(first_line.words) + (list(second_line.words) if second_line else [])
    if end <= 0 or end > len(combined):
        return TailRecovery(article.paragraph, article_score, headword_score, round(score, 4), known_text, "", "geometry-not-found", _raw_lines(article))

    tail: list[str] = []
    known_tokens = _known_tokens(entry)
    if known_tokens:
        suffix = _suffix_from_last_word(known_tokens[-1], combined[end - 1].text)
        if suffix:
            tail.append(suffix)

    # Determine which visual line contains the final matched OCR token.
    if end <= len(first_line.words):
        end_line_idx = line_idx
        end_pos_in_line = end
    else:
        end_line_idx = line_idx + 1
        end_pos_in_line = end - len(first_line.words)

    current_line = article.lines[end_line_idx]
    for word in current_line.words[end_pos_in_line:]:
        reason = _is_stop_token(word.text)
        if reason:
            return TailRecovery(article.paragraph, round(article_score, 4), round(headword_score, 4), round(score, 4), known_text, " ".join(tail).strip(), reason, _raw_lines(article))
        tail.append(word.text)

    # Only walk downward in the same cropped column, one physical line at a
    # time, and stop as soon as a new article appears. Limit continuation to a
    # small number of lines: inflection tails are short; longer walks are more
    # likely to be an OCR grouping error and should go to review.
    max_follow_lines = 3
    for offset, line in enumerate(article.lines[end_line_idx + 1 : end_line_idx + 1 + max_follow_lines], start=1):
        if _looks_like_new_headword_line(line):
            return TailRecovery(article.paragraph, round(article_score, 4), round(headword_score, 4), round(score, 4), known_text, " ".join(tail).strip(), "next-headword-line", _raw_lines(article))
        for word in line.words:
            reason = _is_stop_token(word.text)
            if reason:
                return TailRecovery(article.paragraph, round(article_score, 4), round(headword_score, 4), round(score, 4), known_text, " ".join(tail).strip(), reason, _raw_lines(article))
            tail.append(word.text)

    if end_line_idx + 1 + max_follow_lines < len(article.lines):
        stop_reason = "review-follow-line-limit"
    else:
        stop_reason = "article-end"
    return TailRecovery(article.paragraph, round(article_score, 4), round(headword_score, 4), round(score, 4), known_text, " ".join(tail).strip(), stop_reason, _raw_lines(article))


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
