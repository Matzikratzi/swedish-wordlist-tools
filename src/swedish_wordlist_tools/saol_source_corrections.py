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


SUSPECTED_SAOL_SOURCE_ERRORS: tuple[SaolSourceCorrection, ...] = (
    SaolSourceCorrection(
        lemma="anhörig",
        homonym_number="1",
        field="text",
        source_value="pl. -a",
        corrected_value="pl. +a",
        reason=(
            "The literal replacement notation would combine the compound prefix "
            "from an|hör·ig with -a and produce ana. The attested plural is "
            "anhöriga, so the source notation is treated as a likely sign error."
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


def source_correction_rows() -> list[dict[str, str]]:
    """Return report-friendly rows for all suspected SAOL source errors."""

    return [
        {
            "lemma": item.lemma,
            "homonym_number": item.homonym_number,
            "field": item.field,
            "source_value": item.source_value,
            "corrected_value": item.corrected_value,
            "reason": item.reason,
        }
        for item in SUSPECTED_SAOL_SOURCE_ERRORS
    ]
