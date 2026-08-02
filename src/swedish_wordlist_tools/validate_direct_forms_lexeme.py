from __future__ import annotations

from pathlib import Path
from typing import Any

from . import validate_direct_forms as base
from .compare_sources import _key, _saol_upos
from .jsonl import read_jsonl

_BASE_VALIDATION_ROW = base.validation_row
_REGULAR_NOUN_SUBSET_NOTATIONS = {"+en +ar", "+en +er"}
_SAOL_HOMONYMS: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _set_status(row: dict[str, Any], status: str) -> None:
    row["status"] = status
    row["status_transition"] = (
        f"{row['status_before_completion']}->{status}"
    )


def _casefolded(values: list[str] | set[str]) -> set[str]:
    return {str(value).casefold() for value in values}


def _build_saol_homonym_index(saol_path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index complete generated paradigms for SAOL homonyms.

    Only records with a supported generated paradigm participate. The original
    homonym number and record id are retained so a validation row can explain
    which other SAOL homonym matched SALDO exactly.
    """
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in read_jsonl(saol_path):
        lemma = str(record.get("normaliserat_ord", "")).strip()
        upos = _saol_upos(record)
        if not lemma or not upos:
            continue
        forms = base._record_forms(record)
        if not forms:
            continue
        key = (_key(lemma), upos)
        index.setdefault(key, []).append(
            {
                "record_id": str(record.get("id") or record.get("subnr") or ""),
                "homonym_number": str(record.get("homonr", "")),
                "notation": str(record.get("text", "")),
                "forms": forms,
            }
        )
    return index


def _matching_other_saol_homonyms(
    record: dict[str, Any],
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return other SAOL homonyms whose full paradigm equals SALDO's forms."""
    key = (
        _key(str(record.get("normaliserat_ord", ""))),
        str(row.get("upos", "")),
    )
    candidates = _SAOL_HOMONYMS.get(key, [])
    if len(candidates) < 2:
        return []

    current_record_id = str(record.get("id") or record.get("subnr") or "")
    current_homonym = str(record.get("homonr", ""))
    saldo_forms = _casefolded(row.get("saldo_forms", []))
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        same_record = (
            candidate["record_id"] == current_record_id
            and candidate["homonym_number"] == current_homonym
        )
        if same_record:
            continue
        if _casefolded(candidate["forms"]) == saldo_forms:
            matches.append(candidate)
    return matches


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a validation row with lexeme- and source-aware classification.

    A unique word-form match can point to another lexeme rather than the SAOL
    headword. A same-lemma SALDO analysis can likewise correspond exactly to a
    different SAOL homonym. Separately, for the regular noun patterns
    ``+en +ar`` and ``+en +er``, SALDO sometimes contains only singular forms
    while SAOL explicitly supplies the complete regular plural.
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

    if row["status"] == "form_set_mismatch":
        other_homonyms = _matching_other_saol_homonyms(record, row)
        if other_homonyms:
            _set_status(row, "saldo_matches_other_saol_homonym")
            row["matching_saol_homonyms"] = [
                {
                    "record_id": candidate["record_id"],
                    "homonym_number": candidate["homonym_number"],
                    "notation": candidate["notation"],
                }
                for candidate in other_homonyms
            ]
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
    """Run the existing validator with lexeme- and homonym-aware classification."""
    global _SAOL_HOMONYMS
    previous_homonyms = _SAOL_HOMONYMS
    _SAOL_HOMONYMS = _build_saol_homonym_index(saol_path)
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
        _SAOL_HOMONYMS = previous_homonyms


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
