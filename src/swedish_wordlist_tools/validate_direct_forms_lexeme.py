from __future__ import annotations

from pathlib import Path
from typing import Any

from . import validate_direct_forms as base
from .compare_sources import _key

_BASE_VALIDATION_ROW = base.validation_row


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a validation row and separate form matches to another lexeme.

    A unique word-form match can be useful for finding a SALDO analysis, but it
    is not evidence that the matched SALDO lexeme is the same lexeme as the
    SAOL headword. Keep these rows out of ordinary paradigm mismatches.
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
        row["status"] = "saldo_form_match_other_lexeme"
        row["status_transition"] = (
            f"{row['status_before_completion']}->saldo_form_match_other_lexeme"
        )
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
