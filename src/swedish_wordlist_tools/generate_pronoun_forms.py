from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_notation import apply_form_operation, parse_form_operation
from .saol_surface import clean_saol_word
from .saol_variant_base import prepare_printed_variant_record

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-pronoun-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-pronoun-forms-summary.json")

# The export repeatedly cuts fields at 50 characters.  We may safely retain
# forms already printed before that boundary, but must not call the paradigm
# complete.
_TRUNCATION_LENGTH = 50
_LABELLED_FORM_RE = re.compile(
    r"(?:^|[;,])\s*(?P<label>gen\.|objektsform:|n\.|pl\.|mask\.|best\.)\s*(?P<form>[A-Za-zÅÄÖåäöÉéÜü-]+)",
    re.IGNORECASE,
)
_INLINE_OBJECT_RE = re.compile(r"\bobjektsform:\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", re.IGNORECASE)
_INLINE_GEN_RE = re.compile(r"\bgen\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", re.IGNORECASE)
_INLINE_NEUTER_RE = re.compile(r"\bn\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", re.IGNORECASE)
_INLINE_PLURAL_RE = re.compile(r"\bpl\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", re.IGNORECASE)
_INLINE_MASK_RE = re.compile(r"\bmask\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", re.IGNORECASE)

_EDITORIAL = {
    "anv", "och", "el", "eller", "högt", "i", "sällan", "sing", "substantivisk",
    "uttalat", "vard", "skrivet", "också", "prov", "finl", "pres", "pret", "sup",
}


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


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
        "provenance": "explicit_pronoun_notation" if slot != "lemma" else "lemma",
        "source_token": source,
    })


def _simple_unlabelled_forms(text: str) -> tuple[str, ...]:
    """Return forms only for compact all-form rows with no prose labels.

    Examples: ``ditt dina``, ``erat era``, ``månget många``.  Any punctuation,
    colon, editorial marker or operation token makes the row ineligible; those
    rows are handled by structural patterns instead.
    """

    if not text or any(ch in text for ch in ";,:+_"):
        return ()
    tokens = [token for token in text.split() if token]
    if not 1 <= len(tokens) <= 3:
        return ()
    if any(token.casefold().rstrip(".") in _EDITORIAL for token in tokens):
        return ()
    if any(token.startswith("-") for token in tokens):
        return ()
    return tuple(tokens)


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    if _saol_upos(record) != "PRON":
        return None

    prepared = prepare_printed_variant_record(record)
    lemma = clean_saol_word(prepared.get("normaliserat_ord")) or clean_saol_word(prepared.get("ord"))
    if not lemma:
        return None
    text = _value(prepared, "text").strip()
    forms: list[dict[str, Any]] = []
    seen: set[str] = set()
    _add_form(forms, seen, lemma, "lemma", "")

    # Generic SAOL operations such as +t +a and -t -a.
    for token in re.findall(r"(?<!\S)[+-][^\s,;_]+", text):
        operation = parse_form_operation(token)
        if operation is None:
            continue
        written = apply_form_operation(lemma, operation)
        if written:
            _add_form(forms, seen, written, "inflected", token)

    # Explicitly labelled forms.  These patterns are deliberately narrow so
    # prose like "substantivisk anv." can never become a playable word.
    patterns = (
        ("genitive", _INLINE_GEN_RE),
        ("object", _INLINE_OBJECT_RE),
        ("neuter", _INLINE_NEUTER_RE),
        ("plural", _INLINE_PLURAL_RE),
        ("masculine", _INLINE_MASK_RE),
    )
    for slot, pattern in patterns:
        for match in pattern.finditer(text):
            _add_form(forms, seen, match.group(1), slot, match.group(0))

    # Compact rows consist only of the actual alternative forms.
    for written in _simple_unlabelled_forms(text):
        _add_form(forms, seen, written, "explicit_form", written)

    # Underscore separates explicitly printed alternatives in SAOL, e.g.
    # ``+t +a _ sånt såna``.  Only the branch after '_' is harvested here;
    # the operation branch above already generated +t/+a.
    if "_" in text:
        for branch in text.split("_")[1:]:
            for token in re.findall(r"[A-Za-zÅÄÖåäöÉéÜü-]+", branch):
                folded = token.casefold().rstrip(".")
                if folded in _EDITORIAL:
                    continue
                _add_form(forms, seen, token, "explicit_alternative", token)

    source_truncated = len(text) >= _TRUNCATION_LENGTH
    return {
        "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        "lemma": lemma,
        "homonym_number": _value(record, "homonr"),
        "upos": "PRON",
        "source_notation": text,
        "source_truncated": source_truncated,
        "paradigm_complete": not source_truncated,
        "forms": forms,
    }


def build_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if _saol_upos(record) != "PRON":
            continue
        row = generated_row(record)
        if row is not None:
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate conservative shared SAOL pronoun forms")
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
