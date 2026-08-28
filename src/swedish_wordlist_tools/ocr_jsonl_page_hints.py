from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable

TOKEN_RE = re.compile(r"\S+")


def visible_row_prefix(row: dict[str, Any], text_limit: int = 50) -> str:
    """Return the useful printed prefix of one JSONL article.

    The article/headword part is kept in full.  The free ``text`` field is only
    used as a short positioning/transcription hint; recognition never depends
    on it.
    """
    head = str(row.get("stycke") or row.get("ord") or row.get("normaliserat_ord") or "").strip()
    text = str(row.get("text") or "").strip()[:text_limit]
    if head and text:
        return f"{head} {text}"
    return head or text


def reference_tokens(rows: Iterable[dict[str, Any]], text_limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        prefix = visible_row_prefix(row, text_limit=text_limit)
        for token_index, match in enumerate(TOKEN_RE.finditer(prefix)):
            token = match.group(0)
            out.append(
                {
                    "text": token,
                    "row_index": row_index,
                    "token_index": token_index,
                    "subnr": row.get("subnr"),
                    "ord": row.get("ord"),
                    "stycke": row.get("stycke"),
                    "text_prefix": str(row.get("text") or "")[:text_limit],
                }
            )
    return out


def _norm(s: str) -> str:
    # Keep Swedish letters/digits, but ignore punctuation differences between
    # Tesseract and the JSONL transcription for positioning.
    return "".join(ch.casefold() for ch in s if ch.isalnum() or ch in "åäöéàáèüçñ")


def _similarity(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def align_ocr_words(ocr_words: list[str], refs: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """Monotonically align OCR tokens to JSONL tokens.

    This is deliberately only a hint layer.  We use page order plus fuzzy token
    similarity, and permit unmatched OCR/reference tokens.  Exact raster OCR is
    still authoritative.
    """
    n, m = len(ocr_words), len(refs)
    # Scores favour useful token matches but allow insertions/deletions.  A full
    # O(n*m) table is small for one dictionary page and gives much stabler page
    # positioning than greedy matching after one bad OCR token.
    gap = -0.36
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]  # 1=match,2=skip ocr,3=skip ref
    for i in range(1, n + 1):
        dp[i][0] = i * gap
        back[i][0] = 2
    for j in range(1, m + 1):
        dp[0][j] = j * gap
        back[0][j] = 3
    for i in range(1, n + 1):
        ow = ocr_words[i - 1]
        for j in range(1, m + 1):
            sim = _similarity(ow, str(refs[j - 1].get("text") or ""))
            match_score = dp[i - 1][j - 1] + (2.2 * sim - 0.75)
            skip_ocr = dp[i - 1][j] + gap
            skip_ref = dp[i][j - 1] + gap
            if match_score >= skip_ocr and match_score >= skip_ref:
                dp[i][j] = match_score
                back[i][j] = 1
            elif skip_ocr >= skip_ref:
                dp[i][j] = skip_ocr
                back[i][j] = 2
            else:
                dp[i][j] = skip_ref
                back[i][j] = 3

    out: list[dict[str, Any] | None] = [None] * n
    i, j = n, m
    while i or j:
        op = back[i][j]
        if op == 1:
            sim = _similarity(ocr_words[i - 1], str(refs[j - 1].get("text") or ""))
            # Weak forced matches are not useful enough to prefill a review box.
            if sim >= 0.34:
                item = dict(refs[j - 1])
                item["ocr_text"] = ocr_words[i - 1]
                item["similarity"] = round(sim, 3)
                out[i - 1] = item
            i -= 1
            j -= 1
        elif op == 2:
            i -= 1
        elif op == 3:
            j -= 1
        else:
            # Defensive fallback for the origin/degenerate edge.
            if i:
                i -= 1
            elif j:
                j -= 1
    return out
