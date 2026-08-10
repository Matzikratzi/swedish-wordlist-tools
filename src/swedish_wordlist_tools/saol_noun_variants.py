from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .saol_surface import clean_saol_word

_NULL = {"", "(null)", "null"}
_RELATIVE_TOKEN = re.compile(
    r"^(?:\+[^\s;,]*|pl\.|best\.|n\.|sing\.|obest\.)$",
    re.IGNORECASE,
)


def is_null_text(value: object) -> bool:
    return str(value or "").strip().casefold() in _NULL


def is_cross_reference_row(record: dict[str, Any]) -> bool:
    return (
        str(record.get("ordkl") or "").strip().casefold().startswith("(hv)")
        and is_null_text(record.get("text"))
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        part
        for part in re.split(r"\s+", text.replace(";", " ").replace(",", " ").strip())
        if part
    )


def is_simple_relative_noun_notation(value: object) -> bool:
    """Return true for a single-base noun paradigm safe to rebase on ``ord``.

    This is intentionally narrower than the diagnostic relative-notation class.
    Alternative branches (``_``), ``el.`` and bracket variants can encode more
    than one base spelling, so they are not rebased wholesale here.
    """

    text = str(value or "").strip()
    if is_null_text(text) or "_" in text or "el." in text.casefold() or "[" in text:
        return False
    tokens = _tokens(text)
    return bool(tokens) and any(token.startswith("+") for token in tokens) and all(
        _RELATIVE_TOKEN.fullmatch(token) is not None for token in tokens
    )


def _variant_pair(record: dict[str, Any]) -> tuple[str, str] | None:
    normalized = clean_saol_word(record.get("normaliserat_ord"))
    written = clean_saol_word(record.get("ord"))
    if not normalized or not written or normalized.casefold() == written.casefold():
        return None
    return normalized.casefold(), written.casefold()


def _has_two_alternative_branches(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.count("_") == 1


def prepare_noun_variant_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach conservative sibling evidence before noun generation.

    ``ord`` can be a spelling variant, a phrase-bound form, or a cross-reference
    occurrence, so a written alternative is acted on only when an ``(hv)`` row
    independently confirms the same normalized/written pair.

    Simple one-base relative paradigms are rebased on the confirmed written
    variant (``akne`` -> ``acne``).  For complex rows the alternative is carried
    separately.  Importantly, when SAOL expresses a two-branch ``_`` paradigm,
    the confirmed alternative belongs to the *article*, not only to the duplicate
    source row whose own ``ord`` happens to contain that spelling.  Therefore a
    unique ``(hv)`` alternative is attached to every two-branch NOUN row with the
    same normalized lemma.  This makes both the main and duplicate rows interpret
    e.g. ``bankväsen _ bankväsende`` with the same branch bases.
    """

    materialized = [dict(record) for record in records]
    hv_pairs = {
        pair
        for record in materialized
        if is_cross_reference_row(record)
        for pair in (_variant_pair(record),)
        if pair is not None
    }
    hv_by_normalized: dict[str, set[str]] = defaultdict(set)
    for normalized, written in hv_pairs:
        hv_by_normalized[normalized].add(written)

    result: list[dict[str, Any]] = []
    for record in materialized:
        if _saol_upos(record) != "NOUN":
            result.append(record)
            continue

        normalized = clean_saol_word(record.get("normaliserat_ord"))
        pair = _variant_pair(record)
        own_confirmed_variant = pair is not None and pair in hv_pairs

        # A two-branch article can have its alternative spelling represented in
        # a sibling (hv) row rather than in this particular NOUN row's ``ord``.
        # Bind it only when the article has exactly one confirmed alternative;
        # ambiguous multi-alternative articles remain diagnostic.
        article_alternatives = hv_by_normalized.get(normalized.casefold(), set()) if normalized else set()
        branch_alternative = None
        if _has_two_alternative_branches(record.get("text")) and len(article_alternatives) == 1:
            branch_alternative = next(iter(article_alternatives))

        if not own_confirmed_variant and branch_alternative is None:
            result.append(record)
            continue

        prepared = dict(record)
        prepared["_saol_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
        prepared["_saol_variant_evidence"] = "matching_hv_and_noun_row"

        if own_confirmed_variant and is_simple_relative_noun_notation(record.get("text")):
            prepared["normaliserat_ord"] = clean_saol_word(record.get("ord"))
            prepared["_saol_variant_mode"] = "rebase_simple_relative"
        else:
            written = clean_saol_word(record.get("ord")) if own_confirmed_variant else ""
            alternative = branch_alternative or written
            prepared["_saol_alternative_lemma"] = alternative
            prepared["_saol_variant_mode"] = "additional_lemma"
        result.append(prepared)

    return result
