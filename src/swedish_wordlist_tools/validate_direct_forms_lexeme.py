from __future__ import annotations

from pathlib import Path
from typing import Any

from . import validate_direct_forms as base
from .compare_sources import _key

_BASE_VALIDATION_ROW = base.validation_row
_REGULAR_NOUN_SUBSET_NOTATIONS = {"+en +ar", "+en +er"}


def _set_status(row: dict[str, Any], status: str) -> None:
    row["status"] = status
    row["status_transition"] = (
        f"{row['status_before_completion']}->{status}"
    )


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a validation row with lexeme- and source-aware classification.

    A unique word-form match can point to another lexeme rather than the SAOL
    headword. Separately, for the regular noun patterns ``+en +ar`` and
    ``+en +er``, SALDO sometimes contains only the singular forms while SAOL
    explicitly supplies the complete regular plural. Classify only clean
    SALDO subsets as source differences; conflicting SALDO forms remain real
    mismatches.
    """
    row = _BASE_VALIDATION_ROW(record, match_method, analyses)
    saldo_lemma_keys = {
        _key(str(lemma))
        for analysis in analyses
        for lemma in analysis["lemmas"]
        if lemma
    }
    record_lemma_key = _key(str(record.get("normaliserat_ord", "")))

    if (
        row["status"] == "form_set_mismatch"
        and match_method == "unique_form_same_upos"
        and record_lemma_key
        and record_lemma_key not in saldo_lemma_keys
    ):
        _set_status(row, "saldo_form_match_other_lexeme")
        return row

    if (
        row["status"] == "form_set_mismatch"
        and row.get("upos") == "NOUN"
        and row.get("notation") in _REGULAR_NOUN_SUBSET_NOTATIONS
        and row.get("extra_from_saol")
        and not row.get("missing_from_saol")
    ):
        _set_status(row, "saol_paradigm_differs_from_saldo")

    return row


def validate_direct_forms(
    saol_path: Path = base.DEFAULT_SAOL,
    saldo_path: Path = base.DEFAULT_SALDO,
    jsonl_path: Path = base.DEFAULT_JSONL,
    summary_path: Path = base.DEFAULT_SUMMARY,
) -> dict[str, Any]:
    """Run the existing validator with lexeme-aware row classification."""
    original = base.validation_row
    base.validation_row = validation_row
    try:
        return base.validate_direct_forms(
            saol_path,
            saldo_path,
            jsonl_path,
            summary_path,
        )
    finally:
        base.validation_row = original


def build_parser():
    return base.build_parser()


def main() -> None:
    args = build_parser().parse_args()
    summary = validate_direct_forms(args.saol, args.saldo, args.jsonl, args.summary)
    print(f"Direktmatchade poster: {summary['matched_records']}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(
        "Substantivkomplettering använd: "
        f"{summary['completion_counts'].get('applied', 0)}"
    )
    print("Övergångar efter komplettering:")
    for transition, count in summary["completion_transition_counts"].items():
        print(f"  {transition}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
