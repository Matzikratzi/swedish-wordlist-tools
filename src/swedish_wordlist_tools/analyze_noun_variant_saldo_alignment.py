from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .canonical_form_artifacts import read_artifact_rows
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, build_form_index, read_saldo_forms
from .validate_direct_forms import _analysis_forms

DEFAULT_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-variant-saldo-alignment.txt")
DEFAULT_JSONL = Path("reports/saol14-noun-variant-saldo-alignment.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-variant-saldo-alignment-summary.json")


def _folded(forms: Iterable[str]) -> set[str]:
    return {str(form).casefold() for form in forms if str(form)}


def _status(saol_forms: set[str], saldo_forms: set[str]) -> str:
    left = _folded(saol_forms)
    right = _folded(saldo_forms)
    if left == right:
        return "exact"
    if left and left <= right:
        return "saol_subset"
    if right and right <= left:
        return "saldo_subset"
    if left & right:
        return "overlap"
    return "disjoint"


def _analysis_score(saol_forms: set[str], analysis: dict[str, Any]) -> tuple[int, int, int, int]:
    saldo_forms = set(_analysis_forms(analysis))
    left = _folded(saol_forms)
    right = _folded(saldo_forms)
    return (
        int(left == right),
        int(left <= right),
        len(left & right),
        -len(left ^ right),
    )


def _best_analyses(saol_forms: set[str], analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not analyses:
        return []
    scored = [(_analysis_score(saol_forms, analysis), analysis) for analysis in analyses]
    best = max(score for score, _ in scored)
    return [analysis for score, analysis in scored if score == best]


def _variant_rows(noun_rows: Iterable[dict[str, Any]]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    for row in noun_rows:
        variants = row.get("variant_paradigms") or ()
        if not variants:
            continue
        for variant in variants:
            yield row, variant


def analyze(
    noun_rows: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    article_keys: set[tuple[str, str]] = set()

    for article, variant in _variant_rows(noun_rows):
        lemma = str(variant.get("lemma") or "").strip()
        if not lemma:
            continue
        article_keys.add((str(article.get("record_id") or ""), str(article.get("homonym_number") or "")))
        saol_forms = {
            str(form.get("written_form") or "")
            for form in variant.get("forms", ())
            if str(form.get("written_form") or "")
        }
        analyses = [
            analysis
            for analysis in saldo.get(lemma.casefold(), ())
            if str(analysis.get("upos") or "").upper() == "NOUN"
        ]
        match_method = "lemma_same_upos"
        if not analyses:
            analyses = [
                analysis
                for analysis in form_index.get(lemma.casefold(), ())
                if str(analysis.get("upos") or "").upper() == "NOUN"
            ]
            match_method = "form_same_upos" if analyses else "missing"

        chosen = _best_analyses(saol_forms, analyses)
        saldo_forms = {
            form
            for analysis in chosen
            for form in _analysis_forms(analysis)
        }
        output.append({
            "record_id": str(article.get("record_id") or ""),
            "homonym_number": str(article.get("homonym_number") or ""),
            "article_lemma": str(article.get("lemma") or ""),
            "variant_mode": str(article.get("variant_mode") or ""),
            "variant_lemma": lemma,
            "variant_notation": str(variant.get("notation") or ""),
            "match_method": match_method,
            "status": "missing" if not chosen else _status(saol_forms, saldo_forms),
            "saol_forms": sorted(saol_forms, key=str.casefold),
            "saldo_forms": sorted(saldo_forms, key=str.casefold),
            "extra_from_saol": sorted(saol_forms - saldo_forms, key=str.casefold),
            "missing_from_saol": sorted(saldo_forms - saol_forms, key=str.casefold),
            "saldo_ids": sorted({str(a.get("id") or "") for a in chosen}),
            "saldo_lemmas": sorted({str(l) for a in chosen for l in a.get("lemmas", ())}, key=str.casefold),
            "candidate_count": len(analyses),
            "chosen_count": len(chosen),
        })

    output.sort(key=lambda row: (row["status"], row["article_lemma"].casefold(), row["variant_lemma"].casefold()))
    status_counts = Counter(row["status"] for row in output)
    mode_counts = Counter(row["variant_mode"] for row in output)
    method_counts = Counter(row["match_method"] for row in output)
    summary = {
        "variant_articles": len(article_keys),
        "variant_paradigms": len(output),
        "status_counts": dict(sorted(status_counts.items())),
        "variant_mode_counts": dict(sorted(mode_counts.items())),
        "match_method_counts": dict(sorted(method_counts.items())),
        "non_exact": sum(count for status, count in status_counts.items() if status != "exact"),
    }
    return output, summary


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Variantartiklar: {summary['variant_articles']}",
        f"Variantparadigm: {summary['variant_paradigms']}",
        f"Exakta variantmatchningar: {summary['status_counts'].get('exact', 0)}",
        f"Icke exakta variantmatchningar: {summary['non_exact']}",
        f"Status: {summary['status_counts']}",
        f"Variantlägen: {summary['variant_mode_counts']}",
        f"Matchmetoder: {summary['match_method_counts']}",
        "",
        "Icke exakta varianter:",
    ]
    for row in rows:
        if row["status"] == "exact":
            continue
        lines.append(
            f"  {row['article_lemma']} -> {row['variant_lemma']} "
            f"[{row['variant_mode']}] status={row['status']} method={row['match_method']}"
        )
        lines.append("    SAOL: " + (", ".join(row["saol_forms"]) or "–"))
        lines.append("    SALDO: " + (", ".join(row["saldo_forms"]) or "–"))
        lines.append("    Extra SAOL: " + (", ".join(row["extra_from_saol"]) or "–"))
        lines.append("    Saknas SAOL: " + (", ".join(row["missing_from_saol"]) or "–"))
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SAOL noun article variants against materialized SALDO analyses")
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    noun_rows = read_artifact_rows(args.noun_forms)
    saldo = read_saldo_forms(args.saldo_forms)
    form_index = build_form_index(saldo)
    rows, summary = analyze(noun_rows, saldo, form_index)
    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows, summary), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Variantartiklar: {summary['variant_articles']}")
    print(f"Variantparadigm: {summary['variant_paradigms']}")
    print(f"Exakta: {summary['status_counts'].get('exact', 0)}")
    print(f"Icke exakta: {summary['non_exact']}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
