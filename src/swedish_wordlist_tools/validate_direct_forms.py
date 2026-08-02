from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import (
    _build_form_index,
    _is_affix_entry,
    _key,
    _normalise,
    _saol_upos,
    read_saldo,
)
from .inflect import generate_entry
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSONL = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-direct-form-validation-summary.json")
ZERO_PLURAL_PATTERN = "+et; pl. +"


def _usable_form(value: str) -> bool:
    return bool(value) and not value.rstrip().endswith("-")


def select_direct_match(
    record: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[dict[str, Any]]] | None:
    """Reproduce the direct matching rules used by compare_sources."""
    lemma = _normalise(str(record.get("normaliserat_ord", "")))
    if not lemma or _is_affix_entry(record, lemma):
        return None

    lemma_key = _key(lemma)
    saol_upos = _saol_upos(record)
    analyses = saldo.get(lemma_key, [])
    if analyses:
        matching = [analysis for analysis in analyses if analysis["upos"] == saol_upos]
        if saol_upos and saol_upos != "X" and matching:
            return "lemma_same_upos", matching

        unknown = [analysis for analysis in analyses if not analysis["upos"]]
        if saol_upos and saol_upos != "X" and len(unknown) == 1:
            return "lemma_unknown_saldo_upos", unknown

        saldo_classes = {analysis["upos"] for analysis in analyses}
        if saol_upos in {"", "X"} and len(saldo_classes) == 1 and "" not in saldo_classes:
            return "lemma_inferred_saol_upos", analyses
        return None

    form_candidates = [
        analysis
        for analysis in form_index.get(lemma_key, [])
        if saol_upos and saol_upos != "X" and analysis["upos"] == saol_upos
    ]
    if len(form_candidates) == 1:
        return "unique_form_same_upos", form_candidates
    return None


def _form_status(generated_forms: set[str], saldo_forms: set[str], supported: bool) -> str:
    if not supported:
        return "saol_pattern_unsupported"
    if generated_forms == saldo_forms:
        return "exact_form_set"
    if generated_forms <= saldo_forms:
        return "saol_forms_are_subset"
    return "form_set_mismatch"


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    initial = generate_entry(record)
    generated = complete_noun_entry(record, initial)
    initial_forms = set(initial.forms if initial else ())
    generated_forms = set(generated.forms if generated else ())
    saldo_forms = {
        str(form)
        for analysis in analyses
        for form in analysis["forms"]
        if _usable_form(str(form))
    }

    initial_status = _form_status(initial_forms, saldo_forms, initial is not None)
    status = _form_status(generated_forms, saldo_forms, generated is not None)
    missing_from_saol = saldo_forms - generated_forms
    extra_from_saol = generated_forms - saldo_forms
    completion_applied = generated is not None and generated_forms != initial_forms

    # SAOL's `+et; pl. +` explicitly states that the indefinite plural is
    # identical to the lemma. From that, definite plural in -en follows. SALDO
    # sometimes omits those plural forms (typically for mass/collective nouns)
    # or records another plural. That is a source disagreement, not evidence
    # that the SAOL parser generated an impossible form.
    if (
        status == "form_set_mismatch"
        and initial_status == "saol_forms_are_subset"
        and str(record.get("text", "")).strip() == ZERO_PLURAL_PATTERN
        and completion_applied
    ):
        status = "saol_zero_plural_differs_from_saldo"

    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "lemma": str(record.get("normaliserat_ord", "")),
        "homonym_number": str(record.get("homonr", "")),
        "upos": _saol_upos(record),
        "ordkl": str(record.get("ordkl", "")),
        "notation": str(record.get("text", "")),
        "match_method": match_method,
        "completion_applied": completion_applied,
        "status_before_completion": initial_status,
        "status_transition": f"{initial_status}->{status}",
        "saldo_ids": sorted({str(analysis["id"]) for analysis in analyses}),
        "saldo_lemmas": sorted(
            {str(lemma) for analysis in analyses for lemma in analysis["lemmas"]},
            key=str.casefold,
        ),
        "generated_forms": sorted(generated_forms, key=str.casefold),
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_from_saol": sorted(missing_from_saol, key=str.casefold),
        "extra_from_saol": sorted(extra_from_saol, key=str.casefold),
        "status": status,
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def validate_direct_forms(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    rows: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            continue
        method, analyses = selected
        rows.append(validation_row(record, method, analyses))

    rows.sort(key=lambda row: (str(row["status"]), str(row["lemma"]).casefold()))
    write_jsonl(jsonl_path, rows)

    status_counts = Counter(str(row["status"]) for row in rows)
    method_counts = Counter(str(row["match_method"]) for row in rows)
    completion_counts = Counter(
        "applied" if row["completion_applied"] else "not_applied" for row in rows
    )
    completion_transition_counts = Counter(
        str(row["status_transition"])
        for row in rows
        if row["completion_applied"]
    )
    completion_pattern_transition_counts: dict[str, Counter[str]] = {}
    upos_status_counts: dict[str, Counter[str]] = {}
    for row in rows:
        upos_status_counts.setdefault(str(row["upos"]), Counter())[str(row["status"])] += 1
        if row["completion_applied"]:
            pattern = str(row["notation"])
            completion_pattern_transition_counts.setdefault(pattern, Counter())[
                str(row["status_transition"])
            ] += 1

    summary = {
        "saol": str(saol_path),
        "saldo": str(saldo_path),
        "matched_records": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "match_method_counts": dict(sorted(method_counts.items())),
        "completion_counts": dict(sorted(completion_counts.items())),
        "completion_transition_counts": dict(sorted(completion_transition_counts.items())),
        "completion_pattern_transition_counts": {
            pattern: dict(sorted(counts.items()))
            for pattern, counts in sorted(completion_pattern_transition_counts.items())
        },
        "upos_status_counts": {
            upos: dict(sorted(counts.items()))
            for upos, counts in sorted(upos_status_counts.items())
        },
        "jsonl": str(jsonl_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare forms generated from SAOL notation with SALDO for directly matched records"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


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
