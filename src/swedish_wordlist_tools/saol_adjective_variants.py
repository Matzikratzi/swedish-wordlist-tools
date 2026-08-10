from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .saol_noun_variants import is_cross_reference_row
from .saol_surface import clean_saol_word


def _variant_pair(record: dict[str, Any]) -> tuple[str, str] | None:
    normalized = clean_saol_word(record.get("normaliserat_ord"))
    written = clean_saol_word(record.get("ord"))
    if not normalized or not written or normalized.casefold() == written.casefold():
        return None
    return normalized.casefold(), written.casefold()


def prepare_adjective_variant_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach explicit ``(hv)`` variant evidence to parallel ADJ articles.

    SAOL's normalized key can group a separately written variant under the main
    adjective.  A null-text ``(hv)`` row is direct article evidence for that
    spelling.  When an adjective has exactly two ``_`` branches and exactly one
    such written alternative, expose it to the row interpreter as the base of
    the second branch.  Inflection remains entirely token/slot driven.
    """

    materialized = [dict(record) for record in records]
    hv_by_normalized: dict[str, set[str]] = defaultdict(set)
    for record in materialized:
        if not is_cross_reference_row(record):
            continue
        pair = _variant_pair(record)
        if pair is not None:
            normalized, written = pair
            hv_by_normalized[normalized].add(written)

    result: list[dict[str, Any]] = []
    for record in materialized:
        if str(record.get("upos") or "").upper() != "ADJ":
            result.append(record)
            continue
        text = str(record.get("text") or "").strip()
        normalized = clean_saol_word(record.get("normaliserat_ord")).casefold()
        alternatives = hv_by_normalized.get(normalized, set())
        if text.count("_") == 1 and len(alternatives) == 1:
            prepared = dict(record)
            prepared["_saol_alternative_lemma"] = next(iter(alternatives))
            prepared["_saol_variant_evidence"] = "matching_hv_row"
            result.append(prepared)
        else:
            result.append(record)
    return result
