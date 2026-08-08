from __future__ import annotations

from typing import Any, Iterable

from .classify_form_mismatches import UNCLASSIFIED

SALDO_MISSING_BARE_GENITIVE_S = "saldo_missing_bare_genitive_s"


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def classify_null_genitive_row(row: dict[str, Any]) -> tuple[str, str]:
    if str(row.get("mismatch_classification") or UNCLASSIFIED) != UNCLASSIFIED:
        return UNCLASSIFIED, "already_classified"
    if str(row.get("upos") or "").upper() != "NOUN":
        return UNCLASSIFIED, "not_noun"
    if str(row.get("paradigm_status") or row.get("status") or "") != "form_set_mismatch":
        return UNCLASSIFIED, "not_form_set_mismatch"

    lemma = str(row.get("lemma") or "").casefold()
    notation = str(row.get("notation") or "").strip()
    extra = _casefolded(row.get("extra_from_saol", ()))
    missing = _casefolded(row.get("missing_from_saol", ()))
    if not lemma:
        return UNCLASSIFIED, "missing_lemma"

    if notation in {"", "(null)"} and not missing and extra == {lemma + "s"}:
        return (
            SALDO_MISSING_BARE_GENITIVE_S,
            "SAOL supplies exactly the bare genitive -s form while SALDO lacks it; no other paradigm form differs",
        )

    return UNCLASSIFIED, "no_null_genitive_pattern"
