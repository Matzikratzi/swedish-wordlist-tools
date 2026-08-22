from __future__ import annotations

import re
from dataclasses import dataclass


# Lexicographic/metalinguistic labels are roman even when surrounding form data
# is represented inside an italic markup span in source JSON.
_ROMAN_LABEL = re.compile(
    r"(?i)(?<!\w)(?:s|subst|adj|adv|v|vb|verb|prep|pron|konj|interj|räkn|"
    r"pl|best|obest|pres|pret|sup|imper|inf|komp|superl|neutr|mask|fem|"
    r"gen|dat|ack|nom|el|äv)\."
)

# These separators belong to the roman metalanguage between form strings.
_ROMAN_PUNCT = set(",;()")


@dataclass(frozen=True)
class StyleSegment:
    start: int
    end: int
    text: str
    style: str
    reason: str


def outside_square_brackets(text: str) -> list[tuple[int, int]]:
    """Return half-open ranges outside [...] blocks, supporting nested noise."""
    ranges: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0 and start < i:
                ranges.append((start, i))
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                start = i + 1
    if depth == 0 and start < len(text):
        ranges.append((start, len(text)))
    return ranges


def _mark(mask: list[str | None], start: int, end: int, style: str) -> None:
    for i in range(max(0, start), min(len(mask), end)):
        mask[i] = style


def classify_inflection_text(text: str) -> list[StyleSegment]:
    """Classify SAOL inflection/text typography conservatively.

    Working model confirmed against facsimile examples:
    * actual form strings are italic;
    * grammatical labels/operators are roman;
    * separators between forms are roman;
    * JSONL '+' is semantic repetition notation; the facsimile prints '~';
    * square-bracket material is deliberately excluded for now.

    Whitespace is included with neighboring roman separators where possible but
    is irrelevant to glyph mining.
    """
    mask: list[str | None] = [None] * len(text)
    allowed = [False] * len(text)
    for a, b in outside_square_brackets(text):
        for i in range(a, b):
            allowed[i] = True
            if not text[i].isspace():
                mask[i] = "italic"

    # Grammar labels always override the italic-form default.
    for m in _ROMAN_LABEL.finditer(text):
        if all(allowed[i] for i in range(m.start(), m.end())):
            _mark(mask, m.start(), m.end(), "roman")

    # Punctuation separating form strings is roman. A colon *inside* a lexical
    # form such as a:et is not treated as a separator here.
    for i, ch in enumerate(text):
        if allowed[i] and ch in _ROMAN_PUNCT:
            mask[i] = "roman"

    # A colon at the end of a token is a working SAOL metalanguage rule supplied
    # during review; internal colons remain part of the italic form.
    for m in re.finditer(r"\S+", text):
        token = m.group(0)
        if token.endswith(":") and m.end() - 1 < len(mask) and allowed[m.end() - 1]:
            mask[m.end() - 1] = "roman"

    # Periods belonging to known roman labels are already covered. Other dots
    # remain with their token until we have stronger evidence.
    out: list[StyleSegment] = []
    i = 0
    while i < len(text):
        style = mask[i]
        if style is None:
            i += 1
            continue
        j = i + 1
        while j < len(text) and mask[j] == style:
            j += 1
        raw = text[i:j]
        if raw and not raw.isspace():
            out.append(StyleSegment(i, j, raw, style, "grammar-segmentation"))
        i = j
    return out


def printed_text(text: str) -> str:
    """Map normalized JSONL notation to the glyph actually printed in SAOL."""
    return text.replace("+", "~")
