from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .canonical_form_artifacts import read_artifact_rows
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, read_saldo_forms
from .validate_direct_forms import _analysis_forms

DEFAULT_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-article-saldo-alignment.txt")
DEFAULT_JSONL = Path("reports/saol14-noun-article-saldo-alignment.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-article-saldo-alignment-summary.json")


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
    if not right:
        return "missing"
    return "disjoint"


def _article_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("record_id") or ""), str(row.get("lemma") or "").casefold())


def _variant_lemmas(row: dict[str, Any]) -> tuple[str, ...]:
    values = [str(value or "").strip() for value in row.get("variant_lemmas", ())]
    values = [value for value in values if value]
    if values:
        return tuple(dict.fromkeys(values))
    lemma = str(row.get("lemma") or "").strip()
    return (lemma,) if lemma else ()


def _article_saol_forms(rows: list[dict[str, Any]]) -> set[str]:
    forms: set[str] = set()
    for row in rows:
        variants = row.get("variant_paradigms") or ()
        if variants:
            for variant in variants:
                for form in variant.get("forms", ()):
                    written = str(form.get("written_form") or "")
                    if written:
                        forms.add(written)
        else:
            for form in row.get("forms", ()):
                written = str(form.get("written_form") or "")
                if written:
                    forms.add(written)
    return forms


def _article_variant_lemmas(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for row in rows:
        values.extend(_variant_lemmas(row))
    return tuple(dict.fromkeys(value for value in values if value))


def analyze(
    noun_rows: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in noun_rows:
        if not row.get("variant_paradigms"):
            continue
        grouped.setdefault(_article_key(row), []).append(row)

    output: list[dict[str, Any]] = []
    for (record_id, article_lemma), rows in grouped.items():
        variant_lemmas = _article_variant_lemmas(rows)
        saol_forms = _article_saol_forms(rows)
        analyses: list[dict[str, Any]] = []
        seen: set[int] = set()
        matched_variant_lemmas: list[str] = []
        missing_variant_lemmas: list[str] = []

        for lemma in variant_lemmas:
            candidates = [
                analysis
                for analysis in saldo.get(lemma.casefold(), ())
                if str(analysis.get("upos") or "").upper() == "NOUN"
            ]
            if candidates:
                matched_variant_lemmas.append(lemma)
            else:
                missing_variant_lemmas.append(lemma)
            for analysis in candidates:
                marker = id(analysis)
                if marker in seen:
                    continue
                seen.add(marker)
                analyses.append(analysis)

        saldo_forms = {
            form
            for analysis in analyses
            for form in _analysis_forms(analysis)
        }
        status = _status(saol_forms, saldo_forms)
        row0 = rows[0]
        output.append({
            "record_id": record_id,
            "article_lemma": article_lemma,
            "variant_mode": str(row0.get("variant_mode") or ""),
            "variant_lemmas": list(variant_lemmas),
            "matched_variant_lemmas": matched_variant_lemmas,
            "missing_variant_lemmas": missing_variant_lemmas,
            "saldo_analysis_count": len(analyses),
            "status": status,
            "saol_forms": sorted(saol_forms, key=str.casefold),
            "saldo_forms": sorted(saldo_forms, key=str.casefold),
            "extra_from_saol": sorted(saol_forms - saldo_forms, key=str.casefold),
            "missing_from_saol": sorted(saldo_forms - saol_forms, key=str.casefold),
            "saldo_ids": sorted({str(analysis.get("id") or "") for analysis in analyses}),
            "saldo_lemmas": sorted(
                {str(lemma) for analysis in analyses for lemma in analysis.get("lemmas", ())},
                key=str.casefold,
            ),
        })

    output.sort(key=lambda row: (row["status"], row["article_lemma"]))
    status_counts = Counter(row["status"] for row in output)
    missing_variant_counts = Counter(
        "all_variants_missing" if not row["matched_variant_lemmas"] else
        "some_variants_missing" if row["missing_variant_lemmas"] else
        "all_variants_matched"
        for row in output
    )
    summary = {
        "variant_articles": len(output),
        "status_counts": dict(sorted(status_counts.items())),
        "variant_coverage_counts": dict(sorted(missing_variant_counts.items())),
        "non_exact": sum(count for status, count in status_counts.items() if status != "exact"),
    }
    return output, summary


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Variantartiklar: {summary['variant_articles']}",
        f"Status: {summary['status_counts']}",
        f"Varianttäckning i SALDO: {summary['variant_coverage_counts']}",
        f"Icke exakta artiklar: {summary['non_exact']}",
        "",
        "Icke exakta artiklar:",
    ]
    for row in rows:
        if row["status"] == "exact":
            continue
        lines.append(
            f"  {row['article_lemma']} [{row['variant_mode']}] status={row['status']} "
            f"record_id={row['record_id']}"
        )
        lines.append("    Varianter: " + ", ".join(row["variant_lemmas"]))
        lines.append("    SALDO-matchade varianter: " + (", ".join(row["matched_variant_lemmas"]) or "–"))
        lines.append("    SALDO-saknade varianter: " + (", ".join(row["missing_variant_lemmas"]) or "–"))
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
    parser = argparse.ArgumentParser(description="Audit SAOL noun variant articles against materialized SALDO analyses")
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    noun_rows = read_artifact_rows(args.noun_forms)
    saldo = read_saldo_forms(args.saldo_forms)
    rows, summary = analyze(noun_rows, saldo)
    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows, summary), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Variantartiklar: {summary['variant_articles']}")
    print(f"Status: {summary['status_counts']}")
    print(f"Varianttäckning: {summary['variant_coverage_counts']}")
    print(f"Icke exakta: {summary['non_exact']}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
