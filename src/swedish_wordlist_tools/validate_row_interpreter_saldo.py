from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _build_form_index, read_saldo
from .jsonl import read_jsonl
from .noun_slots import interpret_noun_slots
from .validate_direct_forms import select_direct_match

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-row-interpreter-saldo.txt")
DEFAULT_JSON = Path("reports/saol14-row-interpreter-saldo.json")
DEFAULT_JSONL = Path("reports/saol14-row-interpreter-saldo.jsonl")


def _casefolded(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values if str(value)}


def validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    slots = interpret_noun_slots(record)
    if slots is None:
        return {
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "lemma": str(record.get("normaliserat_ord", "")),
            "notation": str(record.get("text", "")),
            "match_method": match_method,
            "status": "row_interpreter_unsupported",
            "key_forms": [],
            "missing_key_forms_from_saldo": [],
        }

    key_forms = list(slots.written_forms())
    saldo_forms = {
        str(form)
        for analysis in analyses
        for form in analysis.get("forms", ())
        if str(form) and not str(form).rstrip().endswith("-")
    }
    key_folded = _casefolded(key_forms)
    saldo_folded = _casefolded(saldo_forms)
    missing_folded = key_folded - saldo_folded
    missing = sorted(
        {form for form in key_forms if form.casefold() in missing_folded},
        key=str.casefold,
    )

    if not missing:
        status = "all_key_forms_in_saldo"
    elif slots.lemma.casefold() not in saldo_folded:
        status = "lemma_missing_from_saldo_analysis"
    else:
        status = "some_key_forms_missing_from_saldo"

    return {
        "record_id": str(slots.metadata.get("record_id", "")),
        "lemma": slots.lemma,
        "homonym_number": str(slots.metadata.get("homonym_number", "")),
        "notation": slots.notation,
        "ordkl": str(slots.metadata.get("ordkl", "")),
        "match_method": match_method,
        "status": status,
        "key_forms": key_forms,
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_key_forms_from_saldo": missing,
    }


def build_report(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    rows: list[dict[str, Any]] = []
    noun_records = 0
    direct_matches = 0

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "NOUN":
            continue
        noun_records += 1
        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            continue
        direct_matches += 1
        match_method, analyses = selected
        rows.append(validation_row(record, match_method, analyses))

    status_counts = Counter(str(row["status"]) for row in rows)
    missing_form_counts = Counter(
        form
        for row in rows
        for form in row.get("missing_key_forms_from_saldo", ())
    )
    examples = {
        status: [row for row in rows if row["status"] == status][:30]
        for status in status_counts
        if status != "all_key_forms_in_saldo"
    }
    report = {
        "noun_records": noun_records,
        "direct_matches": direct_matches,
        "validated_rows": len(rows),
        "status_counts": dict(status_counts.most_common()),
        "all_key_forms_in_saldo_percent": round(
            100 * status_counts.get("all_key_forms_in_saldo", 0) / len(rows), 2
        ) if rows else 0.0,
        "most_common_missing_key_forms": dict(missing_form_counts.most_common(50)),
        "examples": examples,
    }
    return report, rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Substantivposter: {report['noun_records']}",
        f"Direktmatchade mot SALDO: {report['direct_matches']}",
        f"Validerade rader: {report['validated_rows']}",
        f"Alla nyckelformer finns i SALDO: {report['all_key_forms_in_saldo_percent']:.2f} %",
        "",
        "Status:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")

    for status, rows in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {status}"])
        for row in rows[:20]:
            missing = ", ".join(row.get("missing_key_forms_from_saldo", ()))
            lines.append(
                f"  {row.get('lemma')} | {row.get('notation')} | saknas: {missing}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generic SAOL noun key forms directly against SALDO"
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
    print(f"Substantivposter: {report['noun_records']}")
    print(f"Direktmatchade mot SALDO: {report['direct_matches']}")
    print(f"Alla nyckelformer finns i SALDO: {report['all_key_forms_in_saldo_percent']:.2f} %")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
