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
    """Return true for a single-base noun paradigm safe to rebase on ``ord``."""

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


def _record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identify duplicate JSONL rows that encode one printed SAOL article."""

    record_id = str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or "")
    normalized = clean_saol_word(record.get("normaliserat_ord")).casefold()
    text = " ".join(str(record.get("text") or "").split())
    return record_id, normalized, text


def prepare_noun_variant_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach structural sibling evidence before noun generation.

    ``ord`` is not generally a lemma carrier: it can also contain phrase-bound
    forms and cross-reference material. Two independent structures make it safe:

    * a matching ``(hv)`` row confirms a written alternative;
    * duplicate NOUN rows for the same printed article (same record id,
      normalized lemma and notation) expose distinct ``ord`` spellings. When
      that article has exactly two ``_`` branches and exactly one spelling other
      than the normalized headword, that spelling is the base of branch two.

    The second rule is what SAOL14 uses for e.g. ``hajp``/``hype``: one JSONL row
    has ``ord=hajp`` and the sibling has ``ord=hype``, while the shared notation
    is ``+en; pl. +er el. +ar _ +n [...]``.
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

    noun_written_by_article: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in materialized:
        if _saol_upos(record) != "NOUN" or not _has_two_alternative_branches(record.get("text")):
            continue
        written = clean_saol_word(record.get("ord"))
        if written:
            noun_written_by_article[_record_identity(record)].add(written)

    result: list[dict[str, Any]] = []
    for record in materialized:
        if _saol_upos(record) != "NOUN":
            result.append(record)
            continue

        normalized = clean_saol_word(record.get("normaliserat_ord"))
        pair = _variant_pair(record)
        own_confirmed_variant = pair is not None and pair in hv_pairs

        article_alternatives = set(hv_by_normalized.get(normalized.casefold(), set())) if normalized else set()

        # Duplicate NOUN rows can themselves encode the printed heading variants.
        # Require exact article identity, exactly two branches, and exactly one
        # non-primary spelling before using that spelling as branch-two base.
        sibling_spellings = noun_written_by_article.get(_record_identity(record), set())
        sibling_alternatives = {
            spelling
            for spelling in sibling_spellings
            if normalized and spelling.casefold() != normalized.casefold()
        }
        if len(sibling_alternatives) == 1:
            article_alternatives.update(sibling_alternatives)

        branch_alternative = None
        if _has_two_alternative_branches(record.get("text")) and len(article_alternatives) == 1:
            branch_alternative = next(iter(article_alternatives))

        if not own_confirmed_variant and branch_alternative is None:
            result.append(record)
            continue

        prepared = dict(record)
        prepared["_saol_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
        prepared["_saol_variant_evidence"] = (
            "duplicate_noun_article_rows"
            if branch_alternative in sibling_alternatives
            else "matching_hv_and_noun_row"
        )

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
