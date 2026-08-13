from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_notation import apply_form_operation, parse_form_operation
from .saol_surface import clean_saol_word
from .saol_variant_base import prepare_printed_variant_record
from .saol_wordclasses import classes_from_record, record_for_class

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-adverb-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-adverb-forms-summary.json")

_TRUNCATION_LENGTH = 49
_WORD_RE = re.compile(r"[A-Za-zÅÄÖåäöÉéÜü-]+")
_EDITORIAL = {"komp", "superl", "el", "som", "anv", "vard", "ibl", "i"}
_OPERATION_RE = re.compile(r"(?<!\S)[+-][^\s,;_]+")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value).strip().casefold() in {"", "(null)", "null"}:
        return ""
    return str(value).strip()


def _add_form(forms: list[dict[str, Any]], seen: set[str], written: str, slot: str, source: str) -> None:
    written = clean_saol_word(written)
    if not written or " " in written:
        return
    key = written.casefold()
    if key in seen:
        return
    seen.add(key)
    forms.append({
        "written_form": written,
        "slot": slot,
        "provenance": "lemma" if slot == "lemma" else "explicit_adverb_notation",
        "source_token": source,
    })


def _explicit_words(text: str) -> list[str]:
    lexical_text = _OPERATION_RE.sub(" ", text)
    words: list[str] = []
    for token in _WORD_RE.findall(lexical_text):
        folded = token.casefold().rstrip(".")
        if folded in _EDITORIAL:
            continue
        words.append(token)
    return words


def _adverb_notation(record: dict[str, Any], prepared: dict[str, Any]) -> str:
    """Return only notation that is actually attached to an ADV entry.

    The raw SAOL export has a large class of exact ``ordkl='adv.'`` rows and
    those are lemma-only entries (their text is null in the source data).  Do
    not let an injected or inherited text value turn such a row into an
    inflection paradigm.  Rows whose ordkl itself carries printed notation,
    e.g. ``adv. <i>komp. +re, superl. +st</i>``, may contribute exactly those
    visible comparison forms.  Mixed ADJ+ADV rows are already specialized by
    ``record_for_class`` so adjective-only +t/+a notation is absent here.
    """

    raw_ordkl = str(record.get("ordkl") or "").strip().casefold()
    if raw_ordkl == "adv.":
        return ""
    return _value(prepared, "text")


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    if "ADV" not in classes_from_record(record):
        return None

    class_record = record_for_class(record, "ADV")
    prepared = prepare_printed_variant_record(class_record)
    lemma = clean_saol_word(prepared.get("normaliserat_ord")) or clean_saol_word(prepared.get("ord"))
    if not lemma:
        return None
    text = _adverb_notation(record, prepared)
    forms: list[dict[str, Any]] = []
    seen: set[str] = set()
    _add_form(forms, seen, lemma, "lemma", "")

    # Adverbs have no general inflection paradigm.  Only explicitly printed
    # comparison notation is interpreted here.
    for token in _OPERATION_RE.findall(text):
        operation = parse_form_operation(token)
        if operation is None:
            continue
        written = apply_form_operation(lemma, operation)
        if written:
            _add_form(forms, seen, written, "comparative_or_superlative", token)

    if text:
        for written in _explicit_words(text):
            if written.casefold() == lemma.casefold():
                continue
            _add_form(forms, seen, written, "explicit_form", written)

    source_truncated = len(text) >= _TRUNCATION_LENGTH
    return {
        "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        "lemma": lemma,
        "homonym_number": _value(record, "homonr"),
        "upos": "ADV",
        "source_notation": text,
        "source_truncated": source_truncated,
        "paradigm_complete": not source_truncated,
        "forms": forms,
    }


def build_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if "ADV" not in classes_from_record(record):
            continue
        row = generated_row(record)
        if row is not None:
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate conservative shared SAOL adverb forms")
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
        "truncated_records": sum(1 for row in rows if row["source_truncated"]),
        "unique_forms": len({form["written_form"].casefold() for row in rows for form in row["forms"]}),
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
