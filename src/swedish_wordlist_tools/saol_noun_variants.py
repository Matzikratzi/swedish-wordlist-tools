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
_LEADING_HOMONYM = re.compile(r"^\d+(?=\D)")


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


def _without_homonym_marker(value: object) -> str:
    """Clean a printed headword and remove only a leading homonym digit."""

    return _LEADING_HOMONYM.sub("", clean_saol_word(value))


def _explicit_article_base(record: dict[str, Any]) -> str | None:
    """Return a written article lemma when both ``ord`` and ``stycke`` prove it.

    ``normaliserat_ord`` is an index/grouping key and can collapse a historical
    or alternative headword onto another spelling.  A row may nevertheless be
    its own printed article.  Treat the written surface as the article base only
    when the independently exported ``ord`` and ``stycke`` fields agree after
    presentation cleanup (middle dots, bars, HTML and homonym digit) and both
    differ from ``normaliserat_ord``.

    This captures e.g. ``kapri·foli·um`` stored under normalized ``kaprifol``.
    It deliberately does not capture ``hall|ländska``/``halländska`` (where
    ``ord`` carries morphology rather than a distinct spelling), ``acne`` under
    ``akne`` (where ``stycke`` still names the normalized article), or
    ``bankväsende`` under ``bankväsen`` (where the bar-bearing ``stycke`` names
    the primary compound structure).
    """

    normalized = _without_homonym_marker(record.get("normaliserat_ord"))
    written = _without_homonym_marker(record.get("ord"))
    stycke = _without_homonym_marker(record.get("stycke"))
    if not normalized or not written or not stycke:
        return None
    if written.casefold() == normalized.casefold():
        return None
    if written.casefold() != stycke.casefold():
        return None
    return written


def _variant_pair(record: dict[str, Any]) -> tuple[str, str] | None:
    normalized = clean_saol_word(record.get("normaliserat_ord"))
    written = clean_saol_word(record.get("ord"))
    if not normalized or not written or normalized.casefold() == written.casefold():
        return None
    return normalized.casefold(), written.casefold()


def _branch_count(value: object) -> int:
    text = str(value or "").strip()
    return text.count("_") + 1 if text and not is_null_text(text) else 0


def _has_two_alternative_branches(value: object) -> bool:
    return _branch_count(value) == 2


def _record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identify duplicate JSONL rows that encode one printed SAOL article."""

    record_id = str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or "")
    normalized = clean_saol_word(record.get("normaliserat_ord")).casefold()
    text = " ".join(str(record.get("text") or "").split())
    return record_id, normalized, text


def prepare_noun_variant_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach structural sibling and article-surface evidence before generation.

    ``normaliserat_ord`` groups/indexes SAOL rows but is not always the printed
    lemma of an individual article.  Four independent structures can therefore
    select another noun base:

    * matching ``ord`` and ``stycke`` fields can prove that this row is itself a
      separately written article under a normalized grouping key;
    * a matching ``(hv)`` row confirms a written alternative;
    * a ``homonr=0`` NOUN row can share exact article identity with a primary
      NOUN row and carry that article's written variant base;
    * duplicate two-branch NOUN rows can expose the separate bases of ``_``
      branches.

    These are article/variant relations, not inflection paradigms.  Inflection
    tokens are still interpreted independently downstream.
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

    noun_rows_by_article: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        if _saol_upos(record) == "NOUN":
            noun_rows_by_article[_record_identity(record)].append(record)

    noun_written_by_two_branch_article: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for identity, article_rows in noun_rows_by_article.items():
        if not article_rows or not _has_two_alternative_branches(article_rows[0].get("text")):
            continue
        for record in article_rows:
            written = clean_saol_word(record.get("ord"))
            if written:
                noun_written_by_two_branch_article[identity].add(written)

    result: list[dict[str, Any]] = []
    for record in materialized:
        if _saol_upos(record) != "NOUN":
            result.append(record)
            continue

        normalized = clean_saol_word(record.get("normaliserat_ord"))
        written = clean_saol_word(record.get("ord"))
        pair = _variant_pair(record)
        own_confirmed_variant = pair is not None and pair in hv_pairs

        # Some normalized keys contain a second, separately printed article.
        # When both ord and stycke independently name that written headword,
        # rebase this article before considering cross-reference variants.
        article_base = _explicit_article_base(record)
        if article_base is not None:
            prepared = dict(record)
            prepared["_saol_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
            prepared["normaliserat_ord"] = article_base
            prepared["_saol_variant_mode"] = "rebase_article_surface"
            prepared["_saol_variant_evidence"] = "matching_ord_and_stycke"
            result.append(prepared)
            continue

        identity = _record_identity(record)
        article_rows = noun_rows_by_article.get(identity, [])
        # Exact article identity already fixes normalized lemma and notation.
        # A non-zero sibling is therefore enough to prove that a homonr=0 row
        # belongs to the same printed article; do not require its ``ord`` value
        # to equal normaliserat_ord because headings can carry a homonym digit
        # (e.g. ``1ankare``).
        article_has_primary_row = any(
            str(sibling.get("homonr") or "") != "0"
            for sibling in article_rows
        )
        same_article_zero_variant = (
            str(record.get("homonr") or "") == "0"
            and bool(written)
            and bool(normalized)
            and written.casefold() != normalized.casefold()
            and article_has_primary_row
        )

        # A one-branch homonr=0 sibling is already the variant's own paradigm.
        # Rebase the row itself; explicit forms remain explicit and relative
        # operations apply independently to the written variant base.
        if same_article_zero_variant and _branch_count(record.get("text")) == 1:
            prepared = dict(record)
            prepared["_saol_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
            prepared["normaliserat_ord"] = written
            prepared["_saol_variant_mode"] = "rebase_same_article_zero"
            prepared["_saol_variant_evidence"] = "same_article_homonr_zero"
            result.append(prepared)
            continue

        article_alternatives = set(hv_by_normalized.get(normalized.casefold(), set())) if normalized else set()

        sibling_spellings = noun_written_by_two_branch_article.get(identity, set())
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
            prepared["normaliserat_ord"] = written
            prepared["_saol_variant_mode"] = "rebase_simple_relative"
        else:
            alternative = branch_alternative or written
            prepared["_saol_alternative_lemma"] = alternative
            prepared["_saol_variant_mode"] = "additional_lemma"
        result.append(prepared)

    return result
