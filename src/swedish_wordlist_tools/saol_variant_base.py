from __future__ import annotations

from typing import Any

from .analyze_x_routing import _is_hv
from .saol_surface import clean_saol_word


def prepare_printed_variant_record(record: dict[str, Any]) -> dict[str, Any]:
    """Use the printed ``ord`` as base for a real SAOL variant paradigm.

    SAOL14 sometimes exports a full word-class row whose ``normaliserat_ord``
    points at the canonical spelling while ``ord`` contains the alternative
    spelling to which that row's own inflection notation applies.  These rows
    are commonly homonr=0, for example normaliserat_ord=annektion,
    ord=annexion, text='+en +er'.

    Such a row is already a complete paradigm; it must be interpreted from its
    printed spelling rather than from the normalized cross-reference key.
    ``(hv)`` rows are deliberately excluded: they are relation/index rows, not
    independent paradigms.
    """

    if _is_hv(record):
        return record
    printed = clean_saol_word(record.get("ord"))
    normalized = clean_saol_word(record.get("normaliserat_ord"))
    if not printed or not normalized or printed.casefold() == normalized.casefold():
        return record

    prepared = dict(record)
    prepared["_saol_source_normaliserat_ord"] = normalized
    prepared["_saol_variant_base"] = printed
    prepared["normaliserat_ord"] = printed
    prepared["ord"] = printed
    prepared["stycke"] = printed
    return prepared
