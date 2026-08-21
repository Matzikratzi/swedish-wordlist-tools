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
_OCR_DECORATION_TOKENS = {"=", "«", "»", "|", "¦", "¬"}


@dataclass(frozen=True)
class TailRecovery:
    paragraph: int
    article_score: float
    headword_score: float
    known_text_score: float
    known_text: str
    recovered_tail: str
    raw_recovered_tail: str
    stop_reason: str
    raw_article_lines: tuple[str, ...]


def _soft_token(text: str) -> str:
    return normalize_text_for_match(text).strip().lstrip(_MARKER_PREFIX)


def _compact(text: str) -> str:
    return "".join(ch for ch in normalize_text_for_match(text) if ch.isalnum())


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


def _token_similarity(a: str, b: str) -> float:
    aa, bb = _compact(a), _compact(b)
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def locate_known_text(entry: dict[str, object], article: OcrArticle) -> tuple[int, int, int, float] | None:
    """Locate known JSONL text, strongly preferring the correct final token.

    A plain fuzzy window can stop one token early when punctuation/style OCR is
    noisy.  For truncated fields that is disastrous: we then duplicate most of
    the final inflection word.  Therefore the score includes an explicit match
    against JSONL's final known token.
    """
    target = _known_tokens(entry)
    if not target:
        return None
    last_target = target[-1]
    best = None
    best_rank = -1.0
    for line_idx, line in enumerate(article.lines):
        combined = list(line.words)
        if line_idx + 1 < len(article.lines):
            combined += list(article.lines[line_idx + 1].words)
        soft = [_soft_token(w.text) for w in combined]
        for width in range(max(1, len(target) - 2), len(target) + 3):
            for start in range(0, max(0, len(soft) - width + 1)):
                end = start + width
                candidate = [t for t in soft[start:end] if t]
                if not candidate:
                    continue
                body_score = _window_score(target, candidate)
                end_score = _token_similarity(last_target, candidate[-1])
                # The ending token is deliberately strong evidence, because the
                # whole task is to recover what follows that exact truncation.
                rank = 0.65 * body_score + 0.35 * end_score
                if rank > best_rank:
                    best_rank = rank
                    best = (line_idx, start, end, body_score)
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


def _next_headword_targets(next_entry: dict[str, object] | None) -> list[str]:
    if not next_entry:
        return []
    targets: list[str] = []
    for key in ("normaliserat_ord", "stycke", "ord"):
        value = next_entry.get(key)
        if isinstance(value, str) and value:
            compact = _compact(value)
            if compact and compact not in targets:
                targets.append(compact)
    return targets


def _line_starts_next_jsonl_headword(line: OcrLine, next_line: OcrLine | None, targets: list[str]) -> bool:
    if not targets or not line.words:
        return False
    pieces = [w.text for w in line.words[:4]]
    one = _compact(" ".join(pieces))
    two = one
    if next_line is not None:
        two = _compact(" ".join(pieces + [w.text for w in next_line.words[:3]]))
    best = 0.0
    for target in targets:
        for observed in (one, two):
            if not observed:
                continue
            prefix = observed[: max(1, len(target))]
            best = max(best, SequenceMatcher(None, target, prefix).ratio())
            if len(prefix) >= 4 and target.startswith(prefix):
                best = max(best, len(prefix) / len(target))
    return best >= 0.68


def _looks_like_new_headword_line(line: OcrLine) -> bool:
    if not line.words:
        return False
    first = line.words[0]
    token = normalize_text_for_match(first.text).strip()
    if len(token) < 2 or not any(ch.isalpha() for ch in token) or first.left > 82:
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


def _clean_tail_tokens(tokens: list[str]) -> str:
    """Remove OCR-only decoration without inventing lexical content.

    This intentionally does not dictionary-correct words.  Glyph verification
    can do that later.  Here we only remove standalone/fused print ornaments
    and repair unmistakable OCR whitespace around punctuation.
    """
    cleaned: list[str] = []
    for token in tokens:
        t = token.strip()
        if not t or t in _OCR_DECORATION_TOKENS:
            continue
        # SAOL's superscript semantic dot is frequently OCR'd as a leading «.
        # Keep it as an explicit neutral marker so callers can preserve the
        # article structure without confusing it with lexical text.
        if t.startswith("«") or t.startswith("»"):
            t = "· " + t[1:].lstrip()
        # Trailing isolated OCR ornaments are not lexical characters.
        while t and t[-1] in "«»=¦|":
            t = t[:-1].rstrip()
        if t:
            cleaned.append(t)
    text = " ".join(cleaned)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _result(article: OcrArticle, article_score: float, headword_score: float, score: float, known_text: str, tail: list[str], reason: str) -> TailRecovery:
    raw = " ".join(tail).strip()
    return TailRecovery(
        article.paragraph,
        round(article_score, 4),
        round(headword_score, 4),
        round(score, 4),
        known_text,
        _clean_tail_tokens(tail),
        raw,
        reason,
        _raw_lines(article),
    )


def recover_tail(entry: dict[str, object], article: OcrArticle, article_score: float = 0.0, headword_score: float = 0.0, next_entry: dict[str, object] | None = None) -> TailRecovery:
    located = locate_known_text(entry, article)
    known_text = str(entry.get("text") or "")
    if located is None:
        return TailRecovery(article.paragraph, article_score, headword_score, 0.0, known_text, "", "", "known-text-not-found", _raw_lines(article))

    line_idx, start, end, score = located
    first_line = article.lines[line_idx]
    second_line = article.lines[line_idx + 1] if line_idx + 1 < len(article.lines) else None
    combined = list(first_line.words) + (list(second_line.words) if second_line else [])
    if end <= 0 or end > len(combined):
        return TailRecovery(article.paragraph, article_score, headword_score, round(score, 4), known_text, "", "", "geometry-not-found", _raw_lines(article))

    tail: list[str] = []
    known_tokens = _known_tokens(entry)
    if known_tokens:
        suffix = _suffix_from_last_word(known_tokens[-1], combined[end - 1].text)
        if suffix:
            tail.append(suffix)

    if end <= len(first_line.words):
        end_line_idx = line_idx
        end_pos_in_line = end
    else:
        end_line_idx = line_idx + 1
        end_pos_in_line = end - len(first_line.words)

    targets = _next_headword_targets(next_entry)
    current_line = article.lines[end_line_idx]
    for word in current_line.words[end_pos_in_line:]:
        if not targets:
            reason = _is_stop_token(word.text)
            if reason:
                return _result(article, article_score, headword_score, score, known_text, tail, reason)
        tail.append(word.text)

    max_follow_lines = len(article.lines) if targets else 4
    following = article.lines[end_line_idx + 1 : end_line_idx + 1 + max_follow_lines]
    for rel, line in enumerate(following):
        next_line = following[rel + 1] if rel + 1 < len(following) else None
        if _line_starts_next_jsonl_headword(line, next_line, targets):
            return _result(article, article_score, headword_score, score, known_text, tail, "next-jsonl-headword")
        if not targets and _looks_like_new_headword_line(line):
            return _result(article, article_score, headword_score, score, known_text, tail, "next-headword-line")
        for word in line.words:
            if not targets:
                reason = _is_stop_token(word.text)
                if reason:
                    return _result(article, article_score, headword_score, score, known_text, tail, reason)
            tail.append(word.text)

    reason = "next-jsonl-headword-not-found" if targets else ("review-follow-line-limit" if end_line_idx + 1 + max_follow_lines < len(article.lines) else "article-end")
    return _result(article, article_score, headword_score, score, known_text, tail, reason)


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservatively recover text after a known SAOL14 JSONL text prefix.")
    parser.add_argument("tsv", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entry-json")
    source.add_argument("--jsonl", type=Path)
    parser.add_argument("--subnr", type=int)
    parser.add_argument("--next-entry-json")
    args = parser.parse_args()
    if args.entry_json:
        entry = json.loads(args.entry_json)
    else:
        if args.subnr is None:
            parser.error("--subnr is required with --jsonl")
        entry = load_entry(args.jsonl, args.subnr)
    next_entry = json.loads(args.next_entry_json) if args.next_entry_json else None
    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))
    ranked = rank_articles(entry, articles)
    if not ranked:
        raise SystemExit("no OCR articles found")
    best = ranked[0]
    article = next(a for a in articles if a.paragraph == best.paragraph)
    result = recover_tail(entry, article, best.score, best.headword_score, next_entry)
    json.dump(asdict(result), __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
