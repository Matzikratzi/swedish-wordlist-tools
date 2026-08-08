from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_JSON = Path("reports/saol14-vasen-variant-mismatches.json")
DEFAULT_TEXT = Path("reports/saol14-vasen-variant-mismatches.txt")
TARGET_NOTATION = "+det; pl. +, best. pl. +dena _ +t +n"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def _variant_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    variants = row.get("variant_validation")
    return [item for item in variants if isinstance(item, dict)] if isinstance(variants, list) else []


def _source_summary(row: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    provenance = row.get("generated_from_by_form")
    if not isinstance(provenance, dict):
        return result
    for form, sources in provenance.items():
        if not isinstance(sources, list):
            continue
        result[str(form)] = [
            {
                "heading": str(source.get("heading", "")),
                "heading_type": str(source.get("heading_type", "")),
                "article_id": str(source.get("article_id", "")),
            }
            for source in sources
            if isinstance(source, dict)
        ]
    return result


def analyze_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if str(row.get("upos", "")).upper() == "NOUN"
        and str(row.get("notation", "")).strip() == TARGET_NOTATION
        and str(row.get("mismatch_classification", "")) == "unclassified"
    ]
    selected.sort(
        key=lambda row: (
            str(row.get("lemma", "")).casefold(),
            str(row.get("homonym_number", "")),
            str(row.get("record_id", "")),
        )
    )

    article_ids = {str(row.get("record_id", "")) for row in selected}
    homonyms = Counter(str(row.get("homonym_number", "")) for row in selected)
    variant_statuses = Counter(
        str(variant.get("status", ""))
        for row in selected
        for variant in _variant_rows(row)
    )

    details: list[dict[str, Any]] = []
    for row in selected:
        details.append(
            {
                "lemma": str(row.get("lemma", "")),
                "record_id": str(row.get("record_id", "")),
                "homonym_number": str(row.get("homonym_number", "")),
                "coverage_status": str(row.get("coverage_status", "")),
                "paradigm_status": str(row.get("paradigm_status", "")),
                "paradigm_reason": str(row.get("paradigm_reason", "")),
                "match_method": str(row.get("match_method", "")),
                "saol_variant_lemmas": list(row.get("saol_variant_lemmas", [])),
                "generated_forms": list(row.get("generated_forms", [])),
                "saldo_forms": list(row.get("saldo_forms", [])),
                "extra_from_saol": list(row.get("extra_from_saol", [])),
                "missing_from_saol": list(row.get("missing_from_saol", [])),
                "variant_validation": _variant_rows(row),
                "generated_from_by_form": _source_summary(row),
            }
        )

    return {
        "notation": TARGET_NOTATION,
        "rows": len(selected),
        "unique_record_ids": len(article_ids),
        "homonym_counts": dict(sorted(homonyms.items())),
        "variant_status_counts": dict(sorted(variant_statuses.items())),
        "details": details,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 audit: väsen/väsende-variantgruppen",
        "",
        f"Notation: {summary['notation']}",
        f"Rader: {summary['rows']}",
        f"Unika record_id: {summary['unique_record_ids']}",
        "Homonymnummer: " + ", ".join(
            f"{key or '(tomt)'}={value}" for key, value in summary["homonym_counts"].items()
        ),
        "Variantstatus: " + (", ".join(
            f"{key or '(tomt)'}={value}" for key, value in summary["variant_status_counts"].items()
        ) or "(inga variant_validation-rader)"),
    ]

    for row in summary["details"]:
        lines.extend(
            [
                "",
                "=" * 72,
                f"{row['lemma']}  record_id={row['record_id']} homonr={row['homonym_number']}",
                f"coverage={row['coverage_status']} paradigm={row['paradigm_status']} reason={row['paradigm_reason']}",
                f"match_method={row['match_method']}",
                "Varianter: " + (", ".join(row["saol_variant_lemmas"]) or "–"),
                "SAOL: " + (", ".join(row["generated_forms"]) or "–"),
                "SALDO: " + (", ".join(row["saldo_forms"]) or "–"),
                "Extra SAOL: " + (", ".join(row["extra_from_saol"]) or "–"),
                "Saknas SAOL: " + (", ".join(row["missing_from_saol"]) or "–"),
            ]
        )
        variants = row["variant_validation"]
        if variants:
            lines.append("Per variant:")
            for variant in variants:
                lines.extend(
                    [
                        f"  {variant.get('lemma', '')} [{variant.get('heading_type', '')}] status={variant.get('status', '')}",
                        "    SAOL: " + (", ".join(variant.get("generated_forms", [])) or "–"),
                        "    SALDO: " + (", ".join(variant.get("saldo_forms", [])) or "–"),
                        "    Extra: " + (", ".join(variant.get("extra_from_saol", [])) or "–"),
                        "    Saknas: " + (", ".join(variant.get("missing_from_saol", [])) or "–"),
                    ]
                )
    return "\n".join(lines) + "\n"


def analyze_file(
    input_path: Path = DEFAULT_INPUT,
    *,
    json_path: Path = DEFAULT_JSON,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    summary = analyze_rows(read_jsonl(input_path))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analysera kvarvarande väsen/väsende-paradigmmismatchar")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = analyze_file(args.input, json_path=args.json, text_path=args.text)
    print(f"Rader: {summary['rows']}")
    print(f"Unika record_id: {summary['unique_record_ids']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
