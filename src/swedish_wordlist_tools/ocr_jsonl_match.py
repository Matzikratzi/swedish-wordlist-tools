from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .ocr_saol_normalize import article_text_for_match, normalize_text_for_match
from .ocr_tsv_articles import OcrArticle, group_articles, read_words


@dataclass(frozen=True)
class MatchCandidate:
    block: int
    paragraph: int
    score: float
    headword_score: float
    ord_score: float
    stycke_score: float
    text: str


def _compact(text: str) -> str:
    return "".join(ch for ch in normalize_text_for_match(text) if ch.isalnum())


def _prefix_similarity(needle: str, haystack: str) -> float:
    """Compare a known JSONL signal with the beginning of an OCR article.

    OCR may corrupt the headword (abrovink -> abrowink), so use fuzzy prefix
    similarity rather than requiring exact containment.  We deliberately only
    inspect an early window because JSONL signals describe the article head,
    not arbitrary definition text later in the paragraph.
    """
    n = _compact(needle)
    h = _compact(haystack)
    if not n or not h:
        return 0.0
    window = h[: max(len(n) + 8, len(n) * 2)]
    best = 0.0
    min_len = max(1, len(n) - 3)
    max_len = min(len(window), len(n) + 5)
    for length in range(min_len, max_len + 1):
        best = max(best, SequenceMatcher(None, n, window[:length]).ratio())
    return best


def score_article(record: dict[str, object], article: OcrArticle) -> MatchCandidate:
    text = article_text_for_match(article)
    headword = str(record.get("normaliserat_ord") or "")
    ord_value = str(record.get("ord") or "")
    stycke = str(record.get("stycke") or "")

    hs = _prefix_similarity(headword, text)
    os = _prefix_similarity(ord_value, text)
    ss = _prefix_similarity(stycke, text)

    # Literal printed headword is strongest. Structural ord/stycke are useful
    # corroboration but may describe a later split/variant (bollek / boll|lek).
    score = 0.60 * hs + 0.25 * os + 0.15 * ss
    return MatchCandidate(
        block=article.block,
        paragraph=article.paragraph,
        score=round(score, 4),
        headword_score=round(hs, 4),
        ord_score=round(os, 4),
        stycke_score=round(ss, 4),
        text=text,
    )


def rank_articles(record: dict[str, object], articles: Iterable[OcrArticle]) -> list[MatchCandidate]:
    return sorted(
        (score_article(record, article) for article in articles),
        key=lambda item: item.score,
        reverse=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank OCR paragraphs for one SAOL JSONL record.")
    parser.add_argument("tsv", type=Path)
    parser.add_argument("record", help="A JSON object or path to a file containing one JSON object")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    candidate_path = Path(args.record)
    if candidate_path.exists():
        record = json.loads(candidate_path.read_text(encoding="utf-8"))
    else:
        record = json.loads(args.record)

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))

    ranked = rank_articles(record, articles)[: args.top]
    json.dump([asdict(item) for item in ranked], __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
