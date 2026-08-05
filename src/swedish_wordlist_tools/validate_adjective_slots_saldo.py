from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _build_form_index, read_saldo
from .jsonl import read_jsonl
from .saol_source_corrections import (
    apply_saol_source_corrections,
    interpret_corrected_adjective_slots,
    source_correction_rows,
)
from .validate_direct_forms import select_direct_match

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-adjective-slots-saldo.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-slots-saldo.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-slots-saldo.jsonl")


def _folded(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values if str(value)}


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    corrected_record = apply_saol_source_corrections(record)
    slots = interpret_corrected_adjective_slots(record)
    if slots is None:
        return {
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "lemma": str(record.get("normaliserat_ord", "")),
            "notation": str(record.get("text", "")),
            "effective_notation": str(corrected_record.get("text", "")),
            "source_correction_applied": corrected_record is not record,
            "match_method": match_method,
            "status": "adjective_interpreter_unsupported",
            "forms": [],
            "missing_forms": [],
        }

    saldo_forms = {
        str(form)
        for analysis in analyses
        for form in analysis.get("forms", ())
        if str(form) and not str(form).rstrip().endswith("-")
    }
    saldo_folded = _folded(saldo_forms)
    forms = [
        {
            "written_form": form.written_form,
            "slot": form.slot,
            "in_saldo": form.written_form.casefold() in saldo_folded,
        }
        for form in slots.forms
    ]
    missing = [form for form in forms if not form["in_saldo"]]

    if not missing:
        status = "all_slot_forms_in_saldo"
    elif slots.lemma.casefold() not in saldo_folded:
        status = "lemma_missing_from_saldo_analysis"
    else:
        status = "some_slot_forms_missing_from_saldo"

    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "lemma": slots.lemma,
        "homonym_number": str(record.get("homonr") or ""),
        "notation": str(record.get("text") or ""),
        "effective_notation": str(corrected_record.get("text") or ""),
        "source_correction_applied": corrected_record is not record,
        "ordkl": str(record.get("ordkl") or ""),
        "rule": slots.rule,
        "match_method": match_method,
        "status": status,
        "forms": forms,
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_forms": missing,
    }


def build_report(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    rows: list[dict[str, Any]] = []
    adjective_records = 0
    interpreted_records = 0
    direct_matches = 0

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "ADJ":
            continue
        adjective_records += 1
        if interpret_corrected_adjective_slots(record) is None:
            continue
        interpreted_records += 1
        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            continue
        direct_matches += 1
        match_method, analyses = selected
        rows.append(validation_row(record, match_method, analyses))

    status_counts = Counter(str(row["status"]) for row in rows)
    missing_slot_counts = Counter(
        str(form["slot"])
        for row in rows
        for form in row.get("missing_forms", ())
    )
    missing_rule_counts = Counter(
        str(row["rule"])
        for row in rows
        if row.get("missing_forms")
    )
    missing_form_counts = Counter(
        str(form["written_form"])
        for row in rows
        for form in row.get("missing_forms", ())
    )
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["status"] != "all_slot_forms_in_saldo" and len(examples[row["status"]]) < 30:
            examples[row["status"]].append(row)

    corrections_applied = [row for row in rows if row.get("source_correction_applied")]
    report = {
        "adjective_records": adjective_records,
        "interpreted_records": interpreted_records,
        "direct_matches": direct_matches,
        "validated_rows": len(rows),
        "status_counts": dict(status_counts.most_common()),
        "all_slot_forms_in_saldo_percent": round(
            100 * status_counts.get("all_slot_forms_in_saldo", 0) / len(rows), 2
        ) if rows else 0.0,
        "missing_slot_counts": dict(missing_slot_counts.most_common()),
        "missing_rule_counts": dict(missing_rule_counts.most_common()),
        "most_common_missing_forms": dict(missing_form_counts.most_common(100)),
        "examples": dict(examples),
        "source_corrections": source_correction_rows(),
        "source_corrections_applied": len(corrections_applied),
        "source_correction_examples": corrections_applied[:30],
        "note": (
            "SAOL remains normative. SALDO is used only to validate generated forms. "
            "A form missing from SALDO is reported but not rejected. Exact suspected "
            "source errors are corrected through a separate, reportable list."
        ),
    }
    return report, rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Adjektivposter: {report['adjective_records']}",
        f"Tolkade SAOL-poster: {report['interpreted_records']}",
        f"Direktmatchade mot SALDO: {report['direct_matches']}",
        f"Validerade rader: {report['validated_rows']}",
        f"Alla slotformer finns i SALDO: {report['all_slot_forms_in_saldo_percent']:.2f} %",
        f"Dokumenterade SAOL-korrigeringar använda: {report['source_corrections_applied']}",
        "",
        "Status:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")

    lines.extend(["", "Saknade former per slot:"])
    for slot, count in report["missing_slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")

    lines.extend(["", "Saknade former per parserregel:"])
    for rule, count in report["missing_rule_counts"].items():
        lines.append(f"  {count:6d}  {rule}")

    if report.get("source_corrections"):
        lines.extend(["", "Misstänkta SAOL-källfel:"])
        for item in report["source_corrections"]:
            lines.append(
                f"  {item['lemma']}#{item['homonym_number']} | "
                f"{item['source_value']} -> {item['corrected_value']}"
            )
            lines.append(f"    {item['reason']}")
            for evidence in item.get("evidence", ()): 
                lines.append(f"    källa: {evidence}")

    for status, rows in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {status}"])
        for row in rows[:20]:
            missing = ", ".join(
                f"{form['slot']}={form['written_form']}"
                for form in row.get("missing_forms", ())
            )
            lines.append(
                f"  {row.get('lemma')} | {row.get('effective_notation')} | saknas: {missing}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate interpreted SAOL adjective slots against SALDO forms"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report, rows = build_report(args.saol, args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(args.jsonl, rows)
    print(f"Adjektivposter: {report['adjective_records']}")
    print(f"Tolkade SAOL-poster: {report['interpreted_records']}")
    print(f"Direktmatchade mot SALDO: {report['direct_matches']}")
    print(
        "Alla slotformer finns i SALDO: "
        f"{report['all_slot_forms_in_saldo_percent']:.2f} %"
    )
    print(
        "Dokumenterade SAOL-korrigeringar använda: "
        f"{report['source_corrections_applied']}"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
