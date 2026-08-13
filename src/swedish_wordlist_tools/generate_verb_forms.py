from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_variant_base import prepare_printed_variant_record
from .verb_shared_lexeme import interpret_shared_playable_verb_slots
from .verb_form_expansion import expand_regular_first_conjugation

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-verb-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-verb-forms-summary.json")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    prepared = prepare_printed_variant_record(record)
    slots = interpret_shared_playable_verb_slots(prepared)
    if slots is None:
        return None
    slots = expand_regular_first_conjugation(slots)

    forms = [
        {
            "written_form": form.written_form,
            "slot": form.slot,
            "provenance": form.provenance,
            "source_token": form.source,
            "detail": form.provenance_detail,
        }
        for form in slots.forms
    ]

    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "lemma": slots.lemma,
        "homonym_number": _value(record, "homonr"),
        "source_truncated": slots.metadata.get("source_truncated") == "true",
        "source_notation": _value(record, "text"),
        "stycke": _value(prepared, "stycke"),
        "ordkl": _value(record, "ordkl"),
        "source": _value(record, "source"),
        "variant_base": _value(prepared, "_saol_variant_base"),
        "forms": forms,
        "source_record": {
            "normaliserat_ord": record.get("normaliserat_ord"),
            "ord": record.get("ord"),
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
    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
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
        description="Generate the canonical shared SAOL verb-form artifact"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows = build_rows(args.saol)
    summary = {
        "generated_records": len(rows),
        "generated_forms": sum(len(row["forms"]) for row in rows),
        "variant_base_records": sum(1 for row in rows if row.get("variant_base")),
        "artifact": str(args.jsonl),
        "note": (
            "Canonical shared verb-form artifact. Full word-class variant rows are "
            "inflected from their printed ord spelling when it differs from normaliserat_ord."
        ),
    }
    write_jsonl(args.jsonl, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Genererade verbposter: {summary['generated_records']}")
    print(f"Genererade former: {summary['generated_forms']}")
    print(f"Variantbasposter: {summary['variant_base_records']}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
