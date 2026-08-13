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


def _article_id(row: dict[str, Any]) -> str:
    return str(row.get("article_id") or row.get("record_id") or "")


def _variant_lemmas(row: dict[str, Any]) -> tuple[str, ...]:
    values = [str(value or "").strip() for value in row.get("variant_lemmas", ())]
    values = [value for value in values if value]
    if values:
        return tuple(dict.fromkeys(values))
    lemma = str(row.get("lemma") or "").strip()
    return (lemma,) if lemma else ()


def _variant_paradigm_map(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in rows:
        paradigms = row.get("variant_paradigms") or ()
        if paradigms:
            for paradigm in paradigms:
                lemma = str(paradigm.get("lemma") or "").strip()
                if not lemma:
                    continue
                bucket = result.setdefault(lemma, set())
                bucket.update(
                    str(form.get("written_form") or "")
                    for form in paradigm.get("forms", ())
                    if str(form.get("written_form") or "")
                )
        else:
            lemma = str(row.get("lemma") or "").strip()
            if lemma:
                result.setdefault(lemma, set()).update(
                    str(form.get("written_form") or "")
                    for form in row.get("forms", ())
                    if str(form.get("written_form") or "")
                )
    return result


def _saldo_variant_alignment(
    lemma: str,
    saol_forms: set[str],
    saldo: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    analyses = [
        analysis
        for analysis in saldo.get(lemma.casefold(), ())
        if str(analysis.get("upos") or "").upper() == "NOUN"
    ]
    saldo_forms = {
        form
        for analysis in analyses
        for form in _analysis_forms(analysis)
    }
    return {
        "lemma": lemma,
        "status": _status(saol_forms, saldo_forms),
        "saol_forms": sorted(saol_forms, key=str.casefold),
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "only_in_saol": sorted(saol_forms - saldo_forms, key=str.casefold),
        "only_in_saldo": sorted(saldo_forms - saol_forms, key=str.casefold),
        "saldo_analysis_count": len(analyses),
        "saldo_ids": sorted({str(analysis.get("id") or "") for analysis in analyses}),
        "saldo_lemmas": sorted(
            {str(value) for analysis in analyses for value in analysis.get("lemmas", ())},
            key=str.casefold,
        ),
    }


def analyze(
    noun_rows: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in noun_rows:
        if not row.get("variant_paradigms"):
            continue
        grouped.setdefault(_article_id(row), []).append(row)

    output: list[dict[str, Any]] = []
    for article_id, rows in grouped.items():
        row0 = rows[0]
        paradigm_map = _variant_paradigm_map(rows)
        variant_lemmas: list[str] = []
        for row in rows:
            variant_lemmas.extend(_variant_lemmas(row))
        variant_lemmas = list(dict.fromkeys(variant_lemmas))

        variant_rows = [
            _saldo_variant_alignment(lemma, paradigm_map.get(lemma, set()), saldo)
            for lemma in variant_lemmas
        ]
        saol_forms = {form for variant in variant_rows for form in variant["saol_forms"]}
        saldo_forms = {form for variant in variant_rows for form in variant["saldo_forms"]}
        article_status = _status(saol_forms, saldo_forms)
        matched = [variant["lemma"] for variant in variant_rows if variant["status"] != "missing"]
        missing = [variant["lemma"] for variant in variant_rows if variant["status"] == "missing"]

        output.append({
            "article_id": article_id,
            "record_id": str(row0.get("record_id") or article_id),
            "article_lemma": str(row0.get("lemma") or ""),
            "variant_mode": str(row0.get("variant_mode") or ""),
            "source_homonym_numbers": list(row0.get("source_homonym_numbers") or [str(row0.get("homonym_number") or "")]),
            "variant_lemmas": variant_lemmas,
            "variants": variant_rows,
            "matched_variant_lemmas": matched,
            "missing_variant_lemmas": missing,
            "status": article_status,
            "saol_forms": sorted(saol_forms, key=str.casefold),
            "saldo_forms": sorted(saldo_forms, key=str.casefold),
            "only_in_saol": sorted(saol_forms - saldo_forms, key=str.casefold),
            "only_in_saldo": sorted(saldo_forms - saol_forms, key=str.casefold),
        })

    output.sort(key=lambda row: (row["status"], row["article_lemma"].casefold(), row["article_id"]))
    status_counts = Counter(row["status"] for row in output)
    variant_status_counts = Counter(
        variant["status"] for row in output for variant in row["variants"]
    )
    coverage_counts = Counter(
        "all_variants_missing" if not row["matched_variant_lemmas"] else
        "some_variants_missing" if row["missing_variant_lemmas"] else
        "all_variants_matched"
        for row in output
    )
    summary = {
        "variant_articles": len(output),
        "variant_paradigms": sum(len(row["variants"]) for row in output),
        "status_counts": dict(sorted(status_counts.items())),
        "variant_status_counts": dict(sorted(variant_status_counts.items())),
        "variant_coverage_counts": dict(sorted(coverage_counts.items())),
        "non_exact": sum(count for status, count in status_counts.items() if status != "exact"),
    }
    return output, summary


def _render_forms(label: str, forms: list[str], indent: str = "      ") -> list[str]:
    if not forms:
        return [f"{indent}{label}: –"]
    return [f"{indent}{label}: " + ", ".join(forms)]


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Variantartiklar: {summary['variant_articles']}",
        f"Variantparadigm: {summary['variant_paradigms']}",
        f"Artikelstatus: {summary['status_counts']}",
        f"Variantstatus: {summary['variant_status_counts']}",
        f"Varianttäckning i SALDO: {summary['variant_coverage_counts']}",
        f"Icke exakta artiklar: {summary['non_exact']}",
        "",
        "Icke exakta artiklar:",
    ]
    for row in rows:
        if row["status"] == "exact":
            continue
        lines.append("")
        lines.append(
            f"  {row['article_lemma']} [{row['variant_mode']}] "
            f"status={row['status']} article_id={row['article_id']}"
        )
        lines.append("    Varianter:")
        for index, variant in enumerate(row["variants"], start=1):
            lines.append(
                f"      {index}. {variant['lemma']} — status={variant['status']} "
                f"SALDO-analyser={variant['saldo_analysis_count']}"
            )
            lines.extend(_render_forms("SAOL", variant["saol_forms"], "         "))
            lines.extend(_render_forms("SALDO", variant["saldo_forms"], "         "))
            if variant["only_in_saol"]:
                lines.extend(_render_forms("Finns bara i SAOL", variant["only_in_saol"], "         "))
            if variant["only_in_saldo"]:
                lines.extend(_render_forms("Finns bara i SALDO", variant["only_in_saldo"], "         "))
        lines.append(
            "    Artikelunion: "
            f"SAOL={len(row['saol_forms'])} former, SALDO={len(row['saldo_forms'])} former, "
            f"bara SAOL={len(row['only_in_saol'])}, bara SALDO={len(row['only_in_saldo'])}"
        )
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
    print(f"Variantparadigm: {summary['variant_paradigms']}")
    print(f"Artikelstatus: {summary['status_counts']}")
    print(f"Variantstatus: {summary['variant_status_counts']}")
    print(f"Varianttäckning: {summary['variant_coverage_counts']}")
    print(f"Icke exakta: {summary['non_exact']}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
