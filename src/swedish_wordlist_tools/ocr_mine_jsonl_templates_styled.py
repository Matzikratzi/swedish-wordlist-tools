from __future__ import annotations

import re

from . import ocr_mine_jsonl_templates as base
from .ocr_saol_normalize import normalize_text_for_match

# Grammatical / metalanguage labels printed in roman in SAOL's inflection
# field. They must never seed the italic glyph library.
_ROMAN_LABELS = {
    "s.", "s", "subst.", "subst", "adj.", "adj", "v.", "v", "verb.", "verb",
    "adv.", "adv", "prep.", "prep", "pron.", "pron", "konj.", "konj",
    "interj.", "interj", "räkn.", "räkn",
    "pl.", "pl", "best.", "best", "obest.", "obest",
    "pres.", "pres", "pret.", "pret", "sup.", "sup", "imper.", "imper",
    "inf.", "inf", "komp.", "komp", "superl.", "superl",
    "neutr.", "neutr", "mask.", "mask", "fem.", "fem",
    "gen.", "gen", "dat.", "dat", "ack.", "ack", "nom.", "nom",
    "el.", "el", "äv.", "äv", "och", "eller",
}


def _clean_form_token(token: str) -> str:
    token = normalize_text_for_match(token).strip()
    # Separating punctuation in e.g. "~~n;" and "~," is roman according to
    # the facsimile typography. Keep morphology markers at the left edge.
    token = token.strip(";,:")
    return token


def _tokens_from_markup(text: str, tag: str) -> list[str]:
    spans = re.findall(fr"<{tag}>(.*?)</{tag}>", text, flags=re.IGNORECASE | re.DOTALL)
    result: list[str] = []
    for span in spans:
        for raw in span.split():
            token = _clean_form_token(raw)
            if token:
                result.append(token)
    return result


def _tokens_from_k_markup(text: str) -> list[str]:
    return _tokens_from_markup(text, "k")


def _tokens_from_b_markup(text: str) -> list[str]:
    return _tokens_from_markup(text, "b")


def _heuristic_form_tokens(text: str) -> list[str]:
    """Recover likely italic form tokens from plain JSONL text.

    Typography model supplied from the facsimile:
      <b>tvätt|mästare</b> s. <k>~~n</k>; pl. <k>~~ ~</k>,
      best. pl. <k>-mästarna</k>

    Thus grammar/POS labels and separators are roman, while the actual form
    strings are italic. If literal <k> markup exists, it takes precedence.
    """
    result: list[str] = []
    for raw in text.split():
        token = _clean_form_token(raw)
        if not token:
            continue
        if token.casefold() in _ROMAN_LABELS:
            continue
        # Pure punctuation is never an italic training token.
        if not any(ch.isalnum() or ch in "+~-–—" for ch in token):
            continue
        result.append(token)
    return result


def _fallback_headword_tokens(entry: dict[str, object]) -> list[str]:
    """Return only the article headword when old JSONL lacks <b> markup."""
    for key in ("stycke", "ord", "normaliserat_ord"):
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            continue
        cleaned = normalize_text_for_match(value).strip()
        if cleaned:
            return cleaned.split()[:1]
    return []


def _styled_expected_words(entry: dict[str, object], style: str) -> list[str]:
    text = entry.get("text")

    if style == "bold":
        # SAOL article headwords are bold. Prefer the literal typography markup:
        # this gives us a much stronger style label than classifying glyph pixels.
        if isinstance(text, str) and text:
            marked = _tokens_from_b_markup(text)
            if marked:
                return marked
        return _fallback_headword_tokens(entry)

    if style != "italic":
        return _ORIGINAL(entry, style)

    if not isinstance(text, str) or not text:
        return []
    # Inflection/form strings are explicitly marked <k> in the recovered JSONL.
    # Treat those starts as authoritative italic evidence.
    if re.search(r"<k>.*?</k>", text, flags=re.IGNORECASE | re.DOTALL):
        return _tokens_from_k_markup(text)
    return _heuristic_form_tokens(text)


_ORIGINAL = base._expected_words_for_style
base._expected_words_for_style = _styled_expected_words

# The base miner used this as a protection against accidentally treating short
# roman labels as italic. The styled miner already excludes such labels and,
# crucially, SAOL has many legitimate short italic forms (~n, ~ar, etc.).
# Keep the stronger safeguards instead: exact JSONL/OCR token agreement and
# exact Tesseract symbol-label agreement.
base._informative_exact_token = lambda _token: True


if __name__ == "__main__":
    raise SystemExit(base.main())
