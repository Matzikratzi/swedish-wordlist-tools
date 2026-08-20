from __future__ import annotations

import re
import unicodedata

from .ocr_tsv_articles import OcrArticle


_BRACKETED = re.compile(r"\[[^\]]*\]")
_WS = re.compile(r"\s+")

# Characters that may appear as SAOL word-boundary/typographic separators or be
# introduced by OCR for them. They are ignored in the broad fallback matching
# form, but structural matching distinguishes SAOL's half and full boundary
# marks whenever JSONL supplies them.
_WORD_BOUNDARY_MARKS = str.maketrans("", "", "|¦‖ˈˌ·•")
_HALF_BOUNDARY_SUBSTITUTES = str.maketrans({
    "¦": "·",
    "ˈ": "·",
    "ˌ": "·",
    "•": "·",
})
_FULL_BOUNDARY_SUBSTITUTES = str.maketrans({
    "‖": "|",
})
_DASHES = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
})


def normalize_text_for_match(text: str) -> str:
    """Return a broad, conservative SAOL/OCR matching form.

    This is deliberately lossy and MUST NOT be used as reconstructed source
    text. It exists only to compare known JSONL text/headwords with OCR when
    typographic word-boundary marks are unreliable or missing in OCR.
    """

    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASHES)
    text = _BRACKETED.sub(" ", text)
    text = text.translate(_WORD_BOUNDARY_MARKS)
    text = text.casefold()
    text = _WS.sub(" ", text).strip()
    return text


def normalize_headword_structure(text: str) -> str:
    """Normalize a SAOL headword while preserving boundary strength.

    JSONL distinguishes half boundary ``·`` from full boundary ``|`` and both
    may occur in the same headword, e.g. ``abs·cess|bild·ning``. Keep that
    distinction. Only OCR-like substitutes whose strength is reasonably clear
    are canonicalised; ambiguous plain ``|`` remains a full boundary.
    Pronunciation annotations are removed.
    """

    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASHES)
    text = _BRACKETED.sub(" ", text)
    text = text.translate(_HALF_BOUNDARY_SUBSTITUTES)
    text = text.translate(_FULL_BOUNDARY_SUBSTITUTES)
    text = text.casefold()
    text = _WS.sub(" ", text).strip()
    return text


def jsonl_normalized_headword_from_ord(text: str) -> str:
    """Approximate SAOL JSONL ``normaliserat_ord`` from an ``ord`` headword.

    A full boundary ``|`` denotes a compound boundary. Removing it may expose
    the same letter on both sides; the JSONL normalised form collapses that
    doubled boundary letter. Example: ``boll|lek`` -> ``bollek`` (not
    ``bolllek``). Half boundaries ``·`` are simply removed.

    This function is intended for matching/validation only, not for rewriting
    source data.
    """

    text = normalize_headword_structure(text)
    text = text.replace("·", "")

    while "|" in text:
        left, right = text.split("|", 1)
        if left and right and left[-1] == right[0]:
            text = left + right[1:]
        else:
            text = left + right
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
