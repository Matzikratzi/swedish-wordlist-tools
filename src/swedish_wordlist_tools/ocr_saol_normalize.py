from __future__ import annotations

import re
import unicodedata

from .ocr_tsv_articles import OcrArticle


_BRACKETED = re.compile(r"\[[^\]]*\]")
_WS = re.compile(r"\s+")

# Characters that may appear as SAOL word-boundary/typographic separators or be
# introduced by OCR for them. They are ignored for matching only; raw OCR is
# never changed.
_WORD_BOUNDARY_MARKS = str.maketrans("", "", "|¦‖ˈˌ·•")
_DASHES = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
})


def normalize_text_for_match(text: str) -> str:
    """Return a conservative SAOL/OCR matching form.

    This is deliberately lossy and MUST NOT be used as reconstructed source
    text. It exists only to compare known JSONL text/headwords with OCR.
    """

    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASHES)
    text = _BRACKETED.sub(" ", text)
    text = text.translate(_WORD_BOUNDARY_MARKS)
    text = text.casefold()
    text = _WS.sub(" ", text).strip()
    return text


def article_raw_lines(article: OcrArticle) -> list[str]:
    return [" ".join(word.text for word in line.words) for line in article.lines]


def article_text_for_match(article: OcrArticle) -> str:
    """Flatten an OCR article for matching, joining likely line-broken words.

    A trailing hyphen at a physical line break is treated as a continuation
    marker for matching. This lets e.g. ``abro-`` + ``vinsch`` compare as
    ``abrovinsch`` while preserving the original OCR separately.
    """

    lines = article_raw_lines(article)
    if not lines:
        return ""

    joined = lines[0]
    for line in lines[1:]:
        stripped = joined.rstrip()
        if stripped.endswith("-"):
            joined = stripped[:-1] + line.lstrip()
        else:
            joined = stripped + " " + line.lstrip()
    return normalize_text_for_match(joined)
