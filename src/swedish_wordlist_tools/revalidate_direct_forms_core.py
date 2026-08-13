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
    read_artifact_variant_paradigms,
    variant_paradigms_from_artifact,
)
from .compare_sources import _is_affix_entry, _key, _normalise, _saol_upos
from .jsonl import read_jsonl
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, build_form_index, read_saldo_forms
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


def _homonym_score(generated_forms: set[str], analysis: dict[str, Any]) -> tuple[int, int, int, int]:
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


def _same_upos_analyses(
    lemma: str,
    upos: str,
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
    generated_forms: set[str],
) -> list[dict[str, Any]]:
    lemma_key = _key(_normalise(lemma))
    analyses = saldo.get(lemma_key, [])
    matching = [analysis for analysis in analyses if analysis["upos"] == upos]
    if matching:
        return _best_matching_analyses(generated_forms, matching)

    form_candidates = [
        analysis
        for analysis in form_index.get(lemma_key, [])
        if upos and upos != "X" and analysis["upos"] == upos
    ]
    chosen = _best_matching_analyses(generated_forms, form_candidates)
    return chosen if len(chosen) == 1 else []


def _dedupe_analyses(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for analysis in analyses:
        marker = (
            str(analysis.get("id") or ""),
            tuple(str(value) for value in analysis.get("lemmas", ())),
            tuple(sorted(_analysis_forms(analysis), key=str.casefold)),
            str(analysis.get("upos") or ""),
        )
        if marker not in seen:
            seen.add(marker)
            result.append(analysis)
    return result


def select_direct_match_from_artifacts(
    record: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
    generated_forms: set[str],
) -> tuple[str, list[dict[str, Any]]] | None:
    """Match a single-lemma SAOL record to SALDO without generating forms."""

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


def select_article_variant_match_from_artifacts(
    record: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
    generated_forms: set[str],
    variant_paradigms: dict[str, set[str]] | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Match each materialized SAOL lemma variant against SALDO separately.

    A rebased written variant can be the only materialized paradigm for one raw
    JSONL row, e.g. source normaliserat_ord=akne + ord=acne.  That single
    paradigm must still be looked up as ``acne`` rather than falling back to
    the normalized carrier ``akne``.
    """

    if not variant_paradigms:
        return select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)

    upos = _saol_upos(record)
    if not upos or upos == "X":
        return select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)

    primary = _normalise(str(record.get("normaliserat_ord") or "")).casefold()
    if len(variant_paradigms) == 1:
        lemma, forms = next(iter(variant_paradigms.items()))
        if _normalise(lemma).casefold() == primary:
            return select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)
        analyses = _same_upos_analyses(lemma, upos, saldo, form_index, forms)
        if analyses:
            return "single_article_variant_lemma_same_upos", analyses
        return select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)

    selected: list[dict[str, Any]] = []
    matched = 0
    for lemma, forms in variant_paradigms.items():
        analyses = _same_upos_analyses(lemma, upos, saldo, form_index, forms)
        if analyses:
            matched += 1
            selected.extend(analyses)

    selected = _dedupe_analyses(selected)
    if selected:
        method = (
            "article_variant_lemmas_same_upos"
            if matched == len(variant_paradigms)
            else "article_variant_lemmas_same_upos_partial"
        )
        return method, selected

    return select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)


def _variant_validation(
    record: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
    variant_paradigms: dict[str, set[str]] | None,
) -> list[dict[str, Any]]:
    """Validate each materialized SAOL variant separately against SALDO."""

    if not variant_paradigms:
        return []
    upos = _saol_upos(record)
    if not upos or upos == "X":
        return []

    primary = _normalise(str(record.get("normaliserat_ord") or "")).casefold()
    result: list[dict[str, Any]] = []
    for lemma, forms in variant_paradigms.items():
        analyses = _same_upos_analyses(lemma, upos, saldo, form_index, forms)
        saldo_forms = {form for analysis in analyses for form in _analysis_forms(analysis)}
        status = _form_status(forms, saldo_forms, bool(forms)) if analyses else "variant_missing_in_saldo"
        result.append(
            {
                "lemma": lemma,
                "heading_type": "primary" if _normalise(lemma).casefold() == primary else "alternative",
                "status": status,
                "generated_forms": sorted(forms, key=str.casefold),
                "saldo_forms": sorted(saldo_forms, key=str.casefold),
                "extra_from_saol": sorted(forms - saldo_forms, key=str.casefold),
                "missing_from_saol": sorted(saldo_forms - forms, key=str.casefold),
            }
        )
    return result


def _semantic_status(raw_status: str, variant_validation: list[dict[str, Any]]) -> tuple[str, str]:
    """Separate lexical variant coverage from genuine paradigm disagreement."""

    if raw_status != "form_set_mismatch":
        return raw_status, raw_status
    if not variant_validation:
        return "true_form_mismatch", "non_variant_form_difference"

    primary_rows = [row for row in variant_validation if row["heading_type"] == "primary"]
    alternative_rows = [row for row in variant_validation if row["heading_type"] == "alternative"]
    accepted = {"exact_form_set", "exact_form_set_case_difference", "saol_forms_are_subset"}
    primary_ok = bool(primary_rows) and all(row["status"] in accepted for row in primary_rows)
    missing_alternatives = [row for row in alternative_rows if row["status"] == "variant_missing_in_saldo"]
    mismatching_alternatives = [row for row in alternative_rows if row["status"] == "form_set_mismatch"]

    if primary_ok and missing_alternatives:
        return "variant_coverage_difference", "alternative_heading_missing_in_saldo"
    if primary_ok and mismatching_alternatives:
        return "variant_coverage_difference", "alternative_variant_paradigm_difference"
    if any(row["status"] == "variant_missing_in_saldo" for row in variant_validation):
        return "variant_coverage_difference", "partial_variant_coverage"
    return "true_form_mismatch", "variant_structure_does_not_explain_difference"


def canonical_validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
    *,
    generated_forms: set[str],
    generator: str,
    variant_lemmas: tuple[str, ...] = (),
    variant_validation: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    saldo_forms = {form for analysis in analyses for form in _analysis_forms(analysis)}
    status = _form_status(generated_forms, saldo_forms, bool(generated_forms))
    semantic_status, semantic_reason = _semantic_status(status, variant_validation or [])
    row = {
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
        "semantic_status": semantic_status,
        "semantic_reason": semantic_reason,
    }
    if variant_lemmas:
        row["saol_variant_lemmas"] = list(variant_lemmas)
    if variant_validation:
        row["variant_validation"] = variant_validation
    return row


def revalidate_direct_forms(
    saol_path: Path = DEFAULT_SAOL,
    saldo_forms_path: Path = DEFAULT_SALDO_FORMS,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    *,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> dict[str, Any]:
    """Compare only materialized SAOL/SALDO artifacts for NOUN and ADJ."""

    saldo = read_saldo_forms(saldo_forms_path)
    form_index = build_form_index(saldo)
    artifacts = load_word_class_artifacts(noun_path=noun_forms_path, adjective_path=adjective_forms_path)
    noun_variant_paradigms = read_artifact_variant_paradigms(noun_forms_path)
    rows: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        upos = str(record.get("upos") or "").upper()
        artifact_forms = forms_from_artifacts(record, artifacts)
        if upos in ARTIFACT_WORD_CLASSES:
            generated_forms = artifact_forms or set()
            generator = "canonical_artifact" if artifact_forms is not None else "canonical_artifact_missing"
        else:
            generated_forms = canonical_record_forms(record)
            generator = "record_local_canonical"

        paradigms = (
            variant_paradigms_from_artifact(record, noun_variant_paradigms)
            if upos == "NOUN"
            else None
        )
        selected = select_article_variant_match_from_artifacts(
            record,
            saldo,
            form_index,
            generated_forms,
            paradigms,
        )
        if selected is None:
            continue
        method, analyses = selected
        per_variant = _variant_validation(record, saldo, form_index, paradigms)

        rows.append(
            canonical_validation_row(
                record,
                method,
                analyses,
                generated_forms=generated_forms,
                generator=generator,
                variant_lemmas=tuple(paradigms) if paradigms else (),
                variant_validation=per_variant,
            )
        )

    rows.sort(key=lambda row: (str(row["status"]), str(row["lemma"]).casefold()))
    write_jsonl(jsonl_path, rows)

    status_counts = Counter(str(row["status"]) for row in rows)
    semantic_status_counts = Counter(str(row["semantic_status"]) for row in rows)
    semantic_reason_counts = Counter(str(row["semantic_reason"]) for row in rows)
    generator_counts = Counter(str(row["generator"]) for row in rows)
    method_counts = Counter(str(row["match_method"]) for row in rows)
    upos_status_counts: dict[str, Counter[str]] = {}
    for row in rows:
        upos_status_counts.setdefault(str(row["upos"]), Counter())[str(row["status"])] += 1

    summary = {
        "saol": str(saol_path),
        "saldo_forms": str(saldo_forms_path),
        "noun_forms": str(noun_forms_path),
        "adjective_forms": str(adjective_forms_path),
        "comparison": "materialized_form_artifacts_with_article_variants",
        "generator_counts": dict(sorted(generator_counts.items())),
        "match_method_counts": dict(sorted(method_counts.items())),
        "matched_records": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "semantic_status_counts": dict(sorted(semantic_status_counts.items())),
        "semantic_reason_counts": dict(sorted(semantic_reason_counts.items())),
        "upos_status_counts": {
            upos: dict(sorted(counts.items()))
            for upos, counts in sorted(upos_status_counts.items())
        },
        "jsonl": str(jsonl_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
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
    for name, count in summary["generator_counts"].items():
        print(f"{name}: {count}")
    for name, count in summary["status_counts"].items():
        print(f"{name}: {count}")
    print("Semantisk status:")
    for name, count in summary["semantic_status_counts"].items():
        print(f"{name}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")
