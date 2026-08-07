from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _build_form_index, read_saldo
from .saol_source_corrections import source_correction_rows
from .validate_direct_forms import select_direct_match

DEFAULT_GENERATED = Path("reports/saol14-adjective-forms.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-adjective-slots-saldo.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-slots-saldo.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-slots-saldo.jsonl")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _folded(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values if str(value)}


def validation_row(
    generated: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    saldo_forms = {
        str(form)
        for analysis in analyses
        for form in analysis.get("forms", ())
        if str(form) and not str(form).rstrip().endswith("-")
    }
    saldo_folded = _folded(saldo_forms)
    forms = [
        {
            "written_form": str(form.get("written_form") or ""),
            "slot": str(form.get("slot") or ""),
            "provenance": str(form.get("provenance") or ""),
            "source_token": str(form.get("source_token") or ""),
            "operation_base": str(form.get("operation_base") or ""),
            "in_saldo": str(form.get("written_form") or "").casefold() in saldo_folded,
        }
        for form in generated.get("forms", ())
    ]
    missing = [form for form in forms if not form["in_saldo"]]
    lemma = str(generated.get("lemma") or "")

    if not missing:
        status = "all_slot_forms_in_saldo"
    elif lemma.casefold() not in saldo_folded:
        status = "lemma_missing_from_saldo_analysis"
    else:
        status = "some_slot_forms_missing_from_saldo"

    return {
        "record_id": str(generated.get("record_id") or ""),
        "lemma": lemma,
        "homonym_number": str(generated.get("homonym_number") or ""),
        "notation": str(generated.get("source_notation") or ""),
        "effective_notation": str(generated.get("effective_notation") or ""),
        "stycke": str(generated.get("stycke") or ""),
        "source_correction_applied": bool(generated.get("source_correction_applied")),
        "ordkl": str(generated.get("ordkl") or ""),
        "rule": str(generated.get("rule") or ""),
        "match_method": match_method,
        "status": status,
        "forms": forms,
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_forms": missing,
    }


def build_report(
    generated_path: Path = DEFAULT_GENERATED,
    saldo_path: Path = DEFAULT_SALDO,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    generated_rows = list(read_jsonl(generated_path))
    rows: list[dict[str, Any]] = []
    direct_matches = 0

    for generated in generated_rows:
        source_record = dict(generated.get("source_record") or {})
        selected = select_direct_match(source_record, saldo, form_index)
        if selected is None:
            continue
        direct_matches += 1
        match_method, analyses = selected
        rows.append(validation_row(generated, match_method, analyses))

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

    corrections_applied = [
        row for row in generated_rows if row.get("source_correction_applied")
    ]
    report = {
        "generated_records": len(generated_rows),
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
        "generated_artifact": str(generated_path),
        "note": (
            "SAOL remains normative. This validator consumes the canonical generated "
            "adjective-form artifact, including stored provenance, source tokens and "
            "operation bases, and never invokes the adjective interpreter."
        ),
    }
    return report, rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Genererade adjektivposter: {report['generated_records']}",
        f"Direktmatchade mot SALDO: {report['direct_matches']}",
        f"Validerade rader: {report['validated_rows']}",
        f"Alla slotformer finns i SALDO: {report['all_slot_forms_in_saldo_percent']:.2f} %",
        f"Dokumenterade SAOL-korrigeringar använda: {report['source_corrections_applied']}",
        f"Validerad artefakt: {report['generated_artifact']}",
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
        description="Validate the canonical generated SAOL adjective forms against SALDO"
    )
    parser.add_argument("generated", nargs="?", type=Path, default=DEFAULT_GENERATED)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report, rows = build_report(args.generated, args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(args.jsonl, rows)
    print(f"Genererade adjektivposter: {report['generated_records']}")
    print(f"Direktmatchade mot SALDO: {report['direct_matches']}")
    print(
        "Alla slotformer finns i SALDO: "
        f"{report['all_slot_forms_in_saldo_percent']:.2f} %"
    )
    print(
        "Dokumenterade SAOL-korrigeringar använda: "
        f"{report['source_corrections_applied']}"
    )
    print(f"Validerad artefakt: {report['generated_artifact']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
