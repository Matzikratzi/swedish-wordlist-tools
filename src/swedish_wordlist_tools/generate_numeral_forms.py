from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_notation import expand_optional_form_token
from .saol_surface import clean_saol_word
from .saol_variant_base import prepare_printed_variant_record

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-numeral-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-numeral-forms-summary.json")

_LABEL_RE = re.compile(r"^(?:n\.|mask\.)\s+(.+)$", re.IGNORECASE)
_COUNTING_RE = re.compile(r"^vid:\s*uppräkning:\s*ibl\.\s+(.+)$", re.IGNORECASE)


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value).strip().casefold() in {"", "(null)", "null"}:
        return ""
    return str(value).strip()


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    if _saol_upos(record) != "NUM":
        return None

    prepared = prepare_printed_variant_record(record)
    lemma = clean_saol_word(prepared.get("normaliserat_ord")) or clean_saol_word(prepared.get("ord"))
    if not lemma:
        return None
    text = _value(prepared, "text")

    forms: list[dict[str, Any]] = [{
        "written_form": lemma,
        "slot": "lemma",
        "provenance": "lemma",
        "source_token": "",
    }]
    seen = {lemma.casefold()}

    candidate = ""
    slot = ""
    match = _LABEL_RE.match(text)
    if match:
        candidate = match.group(1).strip()
        slot = "neuter" if text.casefold().startswith("n.") else "masculine"
    else:
        match = _COUNTING_RE.match(text)
        if match:
            candidate = match.group(1).strip()
            slot = "counting_variant"
        elif text and not any(ch in text for ch in ";,:+") and " " not in text:
            candidate = text
            slot = "explicit_form"

    if candidate:
        for variant in expand_optional_form_token(candidate):
            written = clean_saol_word(variant)
            if not written or " " in written or written.casefold() in seen:
                continue
            seen.add(written.casefold())
            forms.append({
                "written_form": written,
                "slot": slot,
                "provenance": "explicit_numeral_notation",
                "source_token": text,
            })

    return {
        "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        "lemma": lemma,
        "homonym_number": str(record.get("homonr") or ""),
        "upos": "NUM",
        "source_notation": text,
        "forms": forms,
    }


def build_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if _saol_upos(record) != "NUM":
            continue
        row = generated_row(record)
        if row is not None:
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate conservative shared SAOL numeral forms")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows = build_rows(read_jsonl(args.source))
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.jsonl.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "generated_records": len(rows),
        "generated_forms": sum(len(row["forms"]) for row in rows),
        "unique_forms": len({form["written_form"].casefold() for row in rows for form in row["forms"]}),
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
