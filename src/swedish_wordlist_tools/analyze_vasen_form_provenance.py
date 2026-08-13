from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_VALIDATION = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-vasen-form-provenance.txt")
DEFAULT_JSON = Path("reports/saol14-vasen-form-provenance.json")
TARGET_NOTATION = "+det; pl. +, best. pl. +dena _ +t +n"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def noun_index(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        record_id = str(row.get("record_id", ""))
        if record_id:
            result.setdefault(record_id, []).append(row)
    return result


def provenance_by_form(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        for form in row.get("forms", []):
            if not isinstance(form, dict):
                continue
            written = str(form.get("written_form", ""))
            if not written:
                continue
            result.setdefault(written, [])
            for source in form.get("generated_from") or []:
                if not isinstance(source, dict):
                    continue
                item = {
                    "heading": str(source.get("heading", "")),
                    "heading_type": str(source.get("heading_type", "")),
                    "article_id": str(source.get("article_id", "")),
                }
                if item not in result[written]:
                    result[written].append(item)
    return result


def analyze_rows(validation_rows: Iterable[dict[str, Any]], noun_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    noun_by_record = noun_index(noun_rows)
    selected = [
        row for row in validation_rows
        if str(row.get("upos", "")).upper() == "NOUN"
        and str(row.get("notation", "")).strip() == TARGET_NOTATION
        and str(row.get("mismatch_classification", "")) == "unclassified"
    ]
    selected.sort(key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("homonym_number", ""))))

    details: list[dict[str, Any]] = []
    for row in selected:
        record_id = str(row.get("record_id", ""))
        provenance = provenance_by_form(noun_by_record.get(record_id, []))
        forms = list(row.get("generated_forms", []))
        details.append({
            "lemma": str(row.get("lemma", "")),
            "record_id": record_id,
            "homonym_number": str(row.get("homonym_number", "")),
            "coverage_status": str(row.get("coverage_status", "")),
            "paradigm_status": str(row.get("paradigm_status", "")),
            "paradigm_reason": str(row.get("paradigm_reason", "")),
            "match_method": str(row.get("match_method", "")),
            "generated_forms": forms,
            "saldo_forms": list(row.get("saldo_forms", [])),
            "extra_from_saol": list(row.get("extra_from_saol", [])),
            "missing_from_saol": list(row.get("missing_from_saol", [])),
            "form_provenance": {form: provenance.get(str(form), []) for form in forms},
            "variant_validation": list(row.get("variant_validation", [])),
        })

    return {
        "notation": TARGET_NOTATION,
        "rows": len(selected),
        "unique_record_ids": len({item["record_id"] for item in details}),
        "details": details,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 väsen/väsende: formproveniens",
        "",
        f"Rader: {summary['rows']}",
        f"Unika record_id: {summary['unique_record_ids']}",
    ]
    for row in summary["details"]:
        lines.extend([
            "",
            "=" * 72,
            f"{row['lemma']} record_id={row['record_id']} homonr={row['homonym_number']}",
            f"coverage={row['coverage_status']} paradigm={row['paradigm_status']} reason={row['paradigm_reason']}",
            f"match={row['match_method']}",
            "Extra SAOL: " + (", ".join(row["extra_from_saol"]) or "–"),
            "Saknas SAOL: " + (", ".join(row["missing_from_saol"]) or "–"),
            "Formproveniens:",
        ])
        for form in row["generated_forms"]:
            sources = row["form_provenance"].get(form, [])
            text = ", ".join(f"{s['heading']} [{s['heading_type']}]" for s in sources) or "–"
            lines.append(f"  {form}: {text}")
        lines.append("Per variant:")
        for variant in row["variant_validation"]:
            lines.append(
                f"  {variant.get('lemma','')} [{variant.get('heading_type','')}] "
                f"status={variant.get('status','')}"
            )
            lines.append("    SAOL: " + (", ".join(variant.get("generated_forms", [])) or "–"))
            lines.append("    SALDO: " + (", ".join(variant.get("saldo_forms", [])) or "–"))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit väsen/väsende with per-form canonical provenance")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze_rows(read_jsonl(args.validation), read_jsonl(args.noun_forms))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rader: {summary['rows']}")
    print(f"Unika record_id: {summary['unique_record_ids']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
