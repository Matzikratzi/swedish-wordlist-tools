from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical_direct_forms import canonical_record_forms
from .canonical_form_artifacts import (
    DEFAULT_ADJECTIVE_FORMS,
    DEFAULT_NOUN_FORMS,
    forms_from_artifacts,
    load_word_class_artifacts,
)
from .compare_sources import _build_form_index, read_saldo
from .jsonl import read_jsonl
from .validate_direct_forms import (
    DEFAULT_JSONL,
    DEFAULT_SALDO,
    DEFAULT_SAOL,
    DEFAULT_SUMMARY,
    _analysis_forms,
    _form_status,
    select_direct_match,
    write_jsonl,
)

ARTIFACT_WORD_CLASSES = frozenset({"NOUN", "ADJ"})


def canonical_validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
    *,
    generated_forms: set[str] | None = None,
    generator: str = "record_local_canonical",
) -> dict[str, Any]:
    if generated_forms is None:
        generated_forms = canonical_record_forms(record)
    saldo_forms = {
        form
        for analysis in analyses
        for form in _analysis_forms(analysis)
    }
    status = _form_status(generated_forms, saldo_forms, bool(generated_forms))
    return {
        "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        "lemma": str(record.get("normaliserat_ord") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "upos": str(record.get("upos") or "").upper(),
        "ordkl": str(record.get("ordkl") or ""),
        "notation": str(record.get("text") or ""),
        "match_method": match_method,
        "generator": generator,
        "saldo_ids": sorted({str(analysis["id"]) for analysis in analyses}),
        "saldo_lemmas": sorted(
            {str(lemma) for analysis in analyses for lemma in analysis["lemmas"]},
            key=str.casefold,
        ),
        "generated_forms": sorted(generated_forms, key=str.casefold),
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_from_saol": sorted(saldo_forms - generated_forms, key=str.casefold),
        "extra_from_saol": sorted(generated_forms - saldo_forms, key=str.casefold),
        "status": status,
    }


def revalidate_direct_forms(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    *,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> dict[str, Any]:
    """Revalidate direct SAOL–SALDO matches from canonical artifacts.

    NOUN and ADJ are deliberately read from their already-generated JSONL
    artifacts.  The validator must not run those interpreters again: otherwise
    validation can silently disagree with the forms that are actually exported.
    Other word classes keep their existing record-local path until they have an
    equivalent per-record canonical artifact.
    """

    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    artifacts = load_word_class_artifacts(
        noun_path=noun_forms_path,
        adjective_path=adjective_forms_path,
    )
    rows: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            continue
        method, analyses = selected
        upos = str(record.get("upos") or "").upper()

        artifact_forms = forms_from_artifacts(record, artifacts)
        if upos in ARTIFACT_WORD_CLASSES:
            generated_forms = artifact_forms or set()
            generator = (
                "canonical_artifact"
                if artifact_forms is not None
                else "canonical_artifact_missing"
            )
        else:
            generated_forms = canonical_record_forms(record)
            generator = "record_local_canonical"

        rows.append(
            canonical_validation_row(
                record,
                method,
                analyses,
                generated_forms=generated_forms,
                generator=generator,
            )
        )

    rows.sort(key=lambda row: (str(row["status"]), str(row["lemma"]).casefold()))
    write_jsonl(jsonl_path, rows)

    status_counts = Counter(str(row["status"]) for row in rows)
    generator_counts = Counter(str(row["generator"]) for row in rows)
    upos_status_counts: dict[str, Counter[str]] = {}
    for row in rows:
        upos_status_counts.setdefault(str(row["upos"]), Counter())[str(row["status"])] += 1

    summary = {
        "saol": str(saol_path),
        "saldo": str(saldo_path),
        "noun_forms": str(noun_forms_path),
        "adjective_forms": str(adjective_forms_path),
        "generator": "canonical_artifacts_for_noun_adj",
        "generator_counts": dict(sorted(generator_counts.items())),
        "matched_records": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Revalidate direct SAOL-SALDO matches; NOUN/ADJ are read from "
            "their canonical generated artifacts"
        )
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary = revalidate_direct_forms(
        args.saol,
        args.saldo,
        args.jsonl,
        args.summary,
        noun_forms_path=args.noun_forms,
        adjective_forms_path=args.adjective_forms,
    )
    print(f"Direktmatchade poster: {summary['matched_records']}")
    for generator, count in summary["generator_counts"].items():
        print(f"{generator}: {count}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
