from __future__ import annotations

from pathlib import Path
from typing import Any

from . import validate_direct_forms as base
from .compare_sources import _key, _saol_upos
from .jsonl import read_jsonl

_BASE_VALIDATION_ROW = base.validation_row
_REGULAR_NOUN_SUBSET_NOTATIONS = {
    "+en +ar",
    "+en +er",
    "+n +r",
    "+n +er",
}
_ALTERNATIVE_GENDER_NOTATIONS = {
    "+et el. +en",
    "+en el. +et",
    "+et el. +en; pl. +",
    "+en el. +et; pl. +",
}
_SAOL_HOMONYMS: dict[tuple[str, str], list[dict[str, Any]]] = {}
_SAOL_ENTRIES: list[dict[str, Any]] = []


def _set_status(row: dict[str, Any], status: str) -> None:
    row["status"] = status
    row["status_transition"] = f"{row['status_before_completion']}->{status}"


def _casefolded(values: list[str] | set[str]) -> set[str]:
    return {str(value).casefold() for value in values}


def _build_saol_indexes(
    saol_path: Path,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    homonyms: dict[tuple[str, str], list[dict[str, Any]]] = {}
    entries: list[dict[str, Any]] = []
    for record in read_jsonl(saol_path):
        lemma = str(record.get("normaliserat_ord", "")).strip()
        upos = _saol_upos(record)
        if not lemma or not upos:
            continue
        forms = base._record_forms(record)
        if not forms:
            continue
        entry = {
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "homonym_number": str(record.get("homonr", "")),
            "lemma": lemma,
            "lemma_key": _key(lemma),
            "upos": upos,
            "notation": str(record.get("text", "")),
            "forms": forms,
        }
        entries.append(entry)
        homonyms.setdefault((entry["lemma_key"], upos), []).append(entry)
    return homonyms, entries


def _matching_other_saol_homonyms(record: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    key = (_key(str(record.get("normaliserat_ord", ""))), str(row.get("upos", "")))
    candidates = _SAOL_HOMONYMS.get(key, [])
    if len(candidates) < 2:
        return []
    current_record_id = str(record.get("id") or record.get("subnr") or "")
    current_homonym = str(record.get("homonr", ""))
    saldo_forms = _casefolded(row.get("saldo_forms", []))
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        same_record = candidate["record_id"] == current_record_id and candidate["homonym_number"] == current_homonym
        if not same_record and _casefolded(candidate["forms"]) == saldo_forms:
            matches.append(candidate)
    return matches


def _regular_noun_plural_family(plural: str) -> set[str]:
    if not plural.endswith(("ar", "er")):
        return set()
    return {plural, plural + "s", plural + "na", plural + "nas"}


def _matching_other_saol_lexemes(record: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    missing = _casefolded(row.get("missing_from_saol", []))
    if len(missing) < 2:
        return []
    current_record_id = str(record.get("id") or record.get("subnr") or "")
    current_lemma_key = _key(str(record.get("normaliserat_ord", "")))
    current_upos = str(row.get("upos", ""))
    matches: list[dict[str, Any]] = []
    for candidate in _SAOL_ENTRIES:
        if candidate["record_id"] == current_record_id:
            continue
        if candidate["lemma_key"] == current_lemma_key and candidate["upos"] == current_upos:
            continue
        candidate_forms = _casefolded(candidate["forms"])
        directly_explained = missing <= candidate_forms
        paradigm_explained = any(
            plural in candidate_forms and _regular_noun_plural_family(plural) == missing
            for plural in missing
        )
        if directly_explained or paradigm_explained:
            matches.append(candidate)
    return matches


def _is_i_noun_definite_and_plural_difference(row: dict[str, Any]) -> bool:
    lemma = str(row.get("lemma", "")).casefold()
    if row.get("notation") != "+n +er" or not lemma.endswith("i"):
        return False
    expected_extra = {lemma + "er", lemma + "ers", lemma + "erna", lemma + "ernas"}
    expected_missing = {lemma + "en", lemma + "ens"}
    return _casefolded(row.get("extra_from_saol", [])) == expected_extra and _casefolded(row.get("missing_from_saol", [])) == expected_missing


def _is_missing_neuter_definite(row: dict[str, Any]) -> bool:
    lemma = str(row.get("lemma", "")).casefold()
    if row.get("notation") not in {"+et", "+et; pl. +"}:
        return False
    return (
        _casefolded(row.get("extra_from_saol", [])) == {lemma + "et", lemma + "ets"}
        and not row.get("missing_from_saol")
    )


def _is_zero_plural_vs_ar_plural(row: dict[str, Any]) -> bool:
    lemma = str(row.get("lemma", "")).casefold()
    if row.get("notation") != "+et; pl. +":
        return False
    expected_extra = {lemma + "et", lemma + "ets"}
    expected_missing = {lemma + "ar", lemma + "ars", lemma + "arna", lemma + "arnas"}
    return (
        _casefolded(row.get("extra_from_saol", [])) == expected_extra
        and _casefolded(row.get("missing_from_saol", [])) == expected_missing
    )


def validation_row(record: dict[str, Any], match_method: str, analyses: list[dict[str, Any]]) -> dict[str, Any]:
    row = _BASE_VALIDATION_ROW(record, match_method, analyses)
    saldo_lemma_keys = {
        _key(str(lemma))
        for analysis in analyses
        for lemma in analysis["lemmas"]
        if lemma
    }
    record_lemma_key = _key(str(record.get("normaliserat_ord", "")))

    if row["status"] == "form_set_mismatch" and match_method == "unique_form_same_upos" and record_lemma_key and record_lemma_key not in saldo_lemma_keys:
        _set_status(row, "saldo_form_match_other_lexeme")
        return row

    if row["status"] == "form_set_mismatch":
        other_homonyms = _matching_other_saol_homonyms(record, row)
        if other_homonyms:
            _set_status(row, "saldo_matches_other_saol_homonym")
            row["matching_saol_homonyms"] = [
                {"record_id": c["record_id"], "homonym_number": c["homonym_number"], "notation": c["notation"]}
                for c in other_homonyms
            ]
            return row

    if row["status"] == "form_set_mismatch":
        other_lexemes = _matching_other_saol_lexemes(record, row)
        if other_lexemes:
            _set_status(row, "saldo_forms_explained_by_other_saol_lexeme")
            row["explaining_saol_lexemes"] = [
                {"record_id": c["record_id"], "homonym_number": c["homonym_number"], "lemma": c["lemma"], "upos": c["upos"], "notation": c["notation"]}
                for c in other_lexemes
            ]
            return row

    notation = str(row.get("notation", ""))
    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and notation.startswith("best. +; i: pl. används:") and row.get("extra_from_saol") and not row.get("missing_from_saol"):
        _set_status(row, "saol_explicit_plural_differs_from_saldo")
        return row

    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and _is_i_noun_definite_and_plural_difference(row):
        _set_status(row, "saol_modern_definite_and_plural_differs_from_saldo")
        return row

    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and _is_missing_neuter_definite(row):
        _set_status(row, "saol_neuter_definite_differs_from_saldo")
        return row

    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and _is_zero_plural_vs_ar_plural(row):
        _set_status(row, "saol_zero_plural_differs_from_saldo")
        return row

    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and notation in _ALTERNATIVE_GENDER_NOTATIONS and row.get("extra_from_saol") and not row.get("missing_from_saol"):
        _set_status(row, "saol_alternative_gender_differs_from_saldo")
        return row

    if row["status"] == "form_set_mismatch" and row.get("upos") == "NOUN" and notation in _REGULAR_NOUN_SUBSET_NOTATIONS and row.get("extra_from_saol") and not row.get("missing_from_saol"):
        _set_status(row, "saol_paradigm_differs_from_saldo")

    return row


def validate_direct_forms(
    saol_path: Path = base.DEFAULT_SAOL,
    saldo_path: Path = base.DEFAULT_SALDO,
    jsonl_path: Path = base.DEFAULT_JSONL,
    summary_path: Path = base.DEFAULT_SUMMARY,
) -> dict[str, Any]:
    global _SAOL_HOMONYMS, _SAOL_ENTRIES
    previous_homonyms = _SAOL_HOMONYMS
    previous_entries = _SAOL_ENTRIES
    _SAOL_HOMONYMS, _SAOL_ENTRIES = _build_saol_indexes(saol_path)
    original = base.validation_row
    base.validation_row = validation_row
    try:
        return base.validate_direct_forms(saol_path, saldo_path, jsonl_path, summary_path)
    finally:
        base.validation_row = original
        _SAOL_HOMONYMS = previous_homonyms
        _SAOL_ENTRIES = previous_entries


def build_parser():
    return base.build_parser()


def main() -> None:
    args = build_parser().parse_args()
    summary = validate_direct_forms(args.saol, args.saldo, args.jsonl, args.summary)
    print(f"Direktmatchade poster: {summary['matched_records']}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Substantivkomplettering använd: {summary['completion_counts'].get('applied', 0)}")
    print("Övergångar efter komplettering:")
    for transition, count in summary["completion_transition_counts"].items():
        print(f"  {transition}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
