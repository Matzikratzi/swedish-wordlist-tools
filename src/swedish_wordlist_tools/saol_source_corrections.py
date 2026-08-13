from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SaolSourceCorrection:
    """A narrowly scoped correction for a suspected error in SAOL source data.

    Corrections are kept explicit and reportable. They must not be generalized
    into parser rules unless the same notation is observed repeatedly.
    """

    lemma: str
    homonym_number: str
    field: str
    source_value: str
    corrected_value: str
    reason: str
    evidence: tuple[str, ...] = ()


SUSPECTED_SAOL_SOURCE_ERRORS: tuple[SaolSourceCorrection, ...] = (
    SaolSourceCorrection(
        lemma="anhörig",
        homonym_number="1",
        field="text",
        source_value="pl. -a",
        corrected_value="pl. +a",
        reason=(
            "SAOL 11 explains that when an entry is divided by a vertical bar, "
            "a following hyphen form normally repeats the part after the bar. "
            "Applied literally to an|hör·ig, pl. -a would therefore produce ana. "
            "The attested plural is anhöriga, so the sign is treated as a likely "
            "source error rather than a general parser exception."
        ),
        evidence=(
            "https://runeberg.org/saol/11-6/0013.html",
            "https://runeberg.org/saol/11-6/0010.html",
        ),
    ),
)


def apply_saol_source_corrections(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with any exact, documented source correction applied."""

    lemma = str(record.get("normaliserat_ord") or "").casefold()
    homonym_number = str(record.get("homonr") or "")
    corrected = record
    for item in SUSPECTED_SAOL_SOURCE_ERRORS:
        if lemma != item.lemma or homonym_number != item.homonym_number:
            continue
        if str(record.get(item.field) or "") != item.source_value:
            continue
        if corrected is record:
            corrected = dict(record)
        corrected[item.field] = item.corrected_value
    return corrected


def interpret_corrected_adjective_slots(record: dict[str, Any]):
    """Interpret an adjective after applying exact documented source corrections."""

    from .adjective_slots import interpret_simple_adjective_slots

    return interpret_simple_adjective_slots(apply_saol_source_corrections(record))


def source_correction_rows() -> list[dict[str, Any]]:
    """Return report-friendly rows for all suspected SAOL source errors."""

    return [
        {
            "lemma": item.lemma,
            "homonym_number": item.homonym_number,
            "field": item.field,
            "source_value": item.source_value,
            "corrected_value": item.corrected_value,
            "reason": item.reason,
            "evidence": list(item.evidence),
        }
        for item in SUSPECTED_SAOL_SOURCE_ERRORS
    ]
