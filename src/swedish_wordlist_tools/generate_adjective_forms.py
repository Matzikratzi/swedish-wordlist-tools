from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .adjective_form_provenance import form_provenance_details
from .adjective_variant_interpreter import interpret_adjective_row
from .analyze_adjectives import _value
from .jsonl import read_jsonl
from .saol_adjective_variants import prepare_adjective_variant_records
from .saol_boundaries import restore_replacement_bar_prefix
from .saol_source_corrections import apply_saol_source_corrections

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-adjective-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-adjective-forms-summary.json")


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    corrected = apply_saol_source_corrections(record)
    slots = interpret_adjective_row(corrected)
    if slots is None:
        return None

    lemma = slots.lemma
    stycke = _value(record, "stycke")
    notation = _value(corrected, "text")
    forms = []
    for form in slots.forms:
        written_form = restore_replacement_bar_prefix(
            stycke=stycke,
            lemma=lemma,
            notation=notation,
            written_form=form.written_form,
        )
        provenance = form_provenance_details(
            written_form=written_form,
            lemma=lemma,
            slot=form.slot,
            notation=notation,
            stycke=stycke,
        )
        forms.append({
            "written_form": written_form,
            "slot": form.slot,
            "provenance": provenance.kind,
            "source_token": provenance.source_token,
            "operation_base": provenance.operation_base,
        })

    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "lemma": lemma,
        "homonym_number": _value(record, "homonr"),
        "rule": slots.rule,
        "variant_evidence": _value(record, "_saol_variant_evidence"),
        "alternative_lemma": _value(record, "_saol_alternative_lemma"),
        "source_correction_applied": corrected is not record,
        "source_notation": _value(record, "text"),
        "effective_notation": notation,
        "stycke": stycke,
        "ordkl": _value(record, "ordkl"),
        "source": _value(record, "source"),
        "forms": forms,
        "source_record": {
            "normaliserat_ord": record.get("normaliserat_ord"),
            "homonr": record.get("homonr"),
            "ordkl": record.get("ordkl"),
            "stycke": record.get("stycke"),
            "text": record.get("text"),
            "upos": record.get("upos"),
            "subnr": record.get("subnr"),
            "urspr_lopnr": record.get("urspr_lopnr"),
        },
    }


def build_rows(saol_path: Path = DEFAULT_SAOL) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    records = prepare_adjective_variant_records(read_jsonl(saol_path))
    for record in records:
        if str(record.get("upos", "")).upper() != "ADJ":
            continue
        row = generated_row(record)
        if row is not None:
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the canonical SAOL adjective-form artifact"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows = build_rows(args.saol)
    explicit_variant_rows = [row for row in rows if row["variant_evidence"] == "matching_hv_row"]
    summary = {
        "generated_records": len(rows),
        "generated_forms": sum(len(row["forms"]) for row in rows),
        "explicit_hv_variant_records": len(explicit_variant_rows),
        "explicit_hv_variant_lemmas": sorted({row["lemma"] for row in explicit_variant_rows}),
        "source_corrections_applied": sum(
            1 for row in rows if row["source_correction_applied"]
        ),
        "artifact": str(args.jsonl),
        "note": (
            "This is the canonical generated adjective-form artifact. Each form stores "
            "its provenance, source SAOL token, and operation base. Validators must "
            "consume it and must not run the adjective interpreter again."
        ),
    }
    write_jsonl(args.jsonl, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Genererade adjektivposter: {summary['generated_records']}")
    print(f"Genererade former: {summary['generated_forms']}")
    print(f"Explicita (hv)-variantposter: {summary['explicit_hv_variant_records']}")
    if summary["explicit_hv_variant_lemmas"]:
        print("Explicita (hv)-variantlemma: " + ", ".join(summary["explicit_hv_variant_lemmas"]))
    print(f"JSONL: {args.jsonl}")
    print(f"Sammanfattning: {args.summary}")


if __name__ == "__main__":
    main()
