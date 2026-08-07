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
from .compare_sources import _is_affix_entry, _key, _normalise, _saol_upos
from .jsonl import read_jsonl
from .saldo_form_artifact import (
    DEFAULT_SALDO_FORMS,
    build_form_index,
    read_saldo_forms,
)
from .validate_direct_forms import (
    DEFAULT_JSONL,
    DEFAULT_SAOL,
    DEFAULT_SUMMARY,
    _analysis_forms,
    _form_status,
    write_jsonl,
)

ARTIFACT_WORD_CLASSES = frozenset({"NOUN", "ADJ"})


def _casefolded(forms: set[str]) -> set[str]:
    return {form.casefold() for form in forms}


def _homonym_score(
    generated_forms: set[str], analysis: dict[str, Any]
) -> tuple[int, int, int, int]:
    saldo_forms = _analysis_forms(analysis)
    generated_folded = _casefolded(generated_forms)
    saldo_folded = _casefolded(saldo_forms)
    overlap = len(generated_folded & saldo_folded)
    symmetric_difference = len(generated_folded ^ saldo_folded)
    return (
        int(generated_folded == saldo_folded),
        int(generated_folded <= saldo_folded),
        overlap,
        -symmetric_difference,
    )


def _best_matching_analyses(
    generated_forms: set[str], analyses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(analyses) <= 1 or not generated_forms:
        return analyses
    scored = [(_homonym_score(generated_forms, analysis), analysis) for analysis in analyses]
    best_score = max(score for score, _ in scored)
    return [analysis for score, analysis in scored if score == best_score]


def select_direct_match_from_artifacts(
    record: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
    generated_forms: set[str],
) -> tuple[str, list[dict[str, Any]]] | None:
    """Match a SAOL record to SALDO without generating any forms.

    Homonym resolution is based only on the already-materialized SAOL form set
    passed in by the caller and the already-materialized SALDO form artifact.
    """

    lemma = _normalise(str(record.get("normaliserat_ord", "")))
    if not lemma or _is_affix_entry(record, lemma):
        return None

    lemma_key = _key(lemma)
    saol_upos = _saol_upos(record)
    analyses = saldo.get(lemma_key, [])
    if analyses:
        matching = [analysis for analysis in analyses if analysis["upos"] == saol_upos]
        if saol_upos and saol_upos != "X" and matching:
            return "lemma_same_upos", _best_matching_analyses(generated_forms, matching)

        unknown = [analysis for analysis in analyses if not analysis["upos"]]
        if saol_upos and saol_upos != "X" and unknown:
            chosen = _best_matching_analyses(generated_forms, unknown)
            if len(chosen) == 1:
                return "lemma_unknown_saldo_upos", chosen

        saldo_classes = {analysis["upos"] for analysis in analyses}
        if saol_upos in {"", "X"} and len(saldo_classes) == 1 and "" not in saldo_classes:
            return "lemma_inferred_saol_upos", _best_matching_analyses(generated_forms, analyses)
        return None

    form_candidates = [
        analysis
        for analysis in form_index.get(lemma_key, [])
        if saol_upos and saol_upos != "X" and analysis["upos"] == saol_upos
    ]
    chosen = _best_matching_analyses(generated_forms, form_candidates)
    if len(chosen) == 1:
        return "unique_form_same_upos", chosen
    return None


def canonical_validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
    *,
    generated_forms: set[str],
    generator: str,
) -> dict[str, Any]:
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
    saldo_forms_path: Path = DEFAULT_SALDO_FORMS,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    *,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> dict[str, Any]:
    """Revalidate direct SAOL–SALDO matches from materialized form artifacts.

    NOUN and ADJ forms are read only from their canonical JSONL artifacts.
    SALDO forms are read only from the canonical SALDO JSONL artifact.  The
    comparison and homonym selection do not run either form generator.

    Word classes without a canonical SAOL artifact still use their existing
    record-local form path and are explicitly labelled as such in the output.
    """

    saldo = read_saldo_forms(saldo_forms_path)
    form_index = build_form_index(saldo)
    artifacts = load_word_class_artifacts(
        noun_path=noun_forms_path,
        adjective_path=adjective_forms_path,
    )
    rows: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
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

        selected = select_direct_match_from_artifacts(
            record,
            saldo,
            form_index,
            generated_forms,
        )
        if selected is None:
            continue
        method, analyses = selected

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
        "saldo_forms": str(saldo_forms_path),
        "noun_forms": str(noun_forms_path),
        "adjective_forms": str(adjective_forms_path),
        "comparison": "materialized_form_artifacts",
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
            "Compare materialized SAOL and SALDO form artifacts; NOUN/ADJ are never regenerated"
        )
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary = revalidate_direct_forms(
        args.saol,
        args.saldo_forms,
        args.jsonl,
        args.summary,
        noun_forms_path=args.noun_forms,
        adjective_forms_path=args.adjective_forms,
    )
    print(f"Direktmatchade poster: {summary['matched_records']}")
    print(f"Jämförelse: {summary['comparison']}")
    print(f"SALDO-artefakt: {summary['saldo_forms']}")
    for generator, count in summary["generator_counts"].items():
        print(f"{generator}: {count}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
