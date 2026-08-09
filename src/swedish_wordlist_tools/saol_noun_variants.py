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


def prepare_noun_variant_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach conservative sibling evidence before noun generation.

    SAOL faksimil rows use ``normaliserat_ord`` as a normalization carrier.
    ``ord`` can be a spelling variant, a phrase-bound form, or merely a
    cross-reference form.  We therefore act only when the same normalized/written
    pair occurs both as an ``(hv)`` row and as a real NOUN row.

    * A simple relative ``+`` paradigm is rebased on the written form.  Example:
      normalized ``akne`` + written ``acne`` + ``+n`` -> acne/acnen.
    * A lexical or structurally complex paradigm keeps the normalized base, but
      the written sibling is supplied as an additional lemma form.  Example:
      ``ankare`` + ``ankar`` + explicit ankaret/ankaren/ankarna.

    The function does not add or remove source rows; it only annotates/clones the
    rows passed to the existing noun interpreter.
    """

    materialized = [dict(record) for record in records]
    hv_pairs = {
        pair
        for record in materialized
        if is_cross_reference_row(record)
        for pair in (_variant_pair(record),)
        if pair is not None
    }

    result: list[dict[str, Any]] = []
    for record in materialized:
        if _saol_upos(record) != "NOUN":
            result.append(record)
            continue
        pair = _variant_pair(record)
        if pair is None or pair not in hv_pairs:
            result.append(record)
            continue

        written = clean_saol_word(record.get("ord"))
        prepared = dict(record)
        prepared["_saol_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
        prepared["_saol_variant_evidence"] = "matching_hv_and_noun_row"
        if is_simple_relative_noun_notation(record.get("text")):
            prepared["normaliserat_ord"] = written
            prepared["_saol_variant_mode"] = "rebase_simple_relative"
        else:
            prepared["_saol_alternative_lemma"] = written
            prepared["_saol_variant_mode"] = "additional_lemma"
        result.append(prepared)

    return result
