from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .analyze_adjectives import _interpret_record, _value
from .jsonl import read_jsonl
from .saol_notation import (
    FormOperationKind,
    expand_optional_form_token,
    parse_form_operations,
    tokenize_notation,
)

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSON = Path("reports/saol14-adjective-shared-notation.json")
DEFAULT_TEXT = Path("reports/saol14-adjective-shared-notation.txt")

_SEPARATORS = frozenset({";", ",", "_"})
_LABELS = frozenset({"el.", "pl.", "best.", "mask.", "neutr.", "komp.", "superl.", "h"})


def _is_metadata_token(token: str) -> bool:
    lower = token.casefold()
    return (
        token in _SEPARATORS
        or lower in _LABELS
        or (not token.startswith(("+", "-")) and token.endswith((":", ".")))
    )


def _shared_structure(tokens: tuple[str, ...] | None) -> bool:
    """Return whether tokens form actual SAOL notation rather than plain prose.

    Every ordinary word is a syntactically valid explicit form token. Therefore
    successful tokenization and form parsing alone are not enough: the row must
    also contain a notation marker, such as punctuation/labels or a non-explicit
    form operation (``+``, ``+a``, ``-re`` and so on).
    """

    if not tokens:
        return False
    saw_form = False
    saw_notation_marker = False
    for token in tokens:
        if _is_metadata_token(token):
            saw_notation_marker = True
            continue
        operations = parse_form_operations(token)
        if operations is None:
            return False
        saw_form = True
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            saw_notation_marker = True
    return saw_form and saw_notation_marker


def analyze_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    remaining: list[dict[str, Any]] = []
    pattern_counts: Counter[str] = Counter()
    optional_counts: Counter[str] = Counter()

    adjective_records = 0
    interpreted_records = 0
    tokenizable_records = 0
    shared_structured_records = 0
    optional_records = 0

    for record in records:
        if str(record.get("upos", "")).upper() != "ADJ":
            continue
        adjective_records += 1
        if _interpret_record(record) is not None:
            interpreted_records += 1
            continue

        lemma = _value(record, "normaliserat_ord")
        text = _value(record, "text")
        tokens = tokenize_notation(text) if text else None
        tokenizable = tokens is not None
        structured = _shared_structure(tokens)
        optional_tokens = tuple(
            token
            for token in (tokens or ())
            if len(expand_optional_form_token(token)) > 1
        )

        tokenizable_records += int(tokenizable)
        shared_structured_records += int(structured)
        optional_records += int(bool(optional_tokens))
        pattern_counts[text or "(none)"] += 1
        optional_counts.update(optional_tokens)
        remaining.append(
            {
                "lemma": lemma,
                "homonym_number": _value(record, "homonr"),
                "text": text,
                "stycke": _value(record, "stycke"),
                "tokenizable": tokenizable,
                "shared_structured": structured,
                "optional_tokens": list(optional_tokens),
                "tokens": list(tokens or ()),
            }
        )

    remaining.sort(
        key=lambda row: (
            not row["shared_structured"],
            not row["tokenizable"],
            row["lemma"].casefold(),
            row["homonym_number"],
        )
    )
    return {
        "adjective_records": adjective_records,
        "already_interpreted_records": interpreted_records,
        "remaining_records": len(remaining),
        "remaining_tokenizable_by_shared_layer": tokenizable_records,
        "remaining_structured_by_shared_layer": shared_structured_records,
        "remaining_with_optional_form_tokens": optional_records,
        "optional_token_counts": dict(optional_counts.most_common()),
        "top_remaining_patterns": pattern_counts.most_common(100),
        "records": remaining,
        "note": (
            "This audit does not assign adjective grammatical slots. It identifies "
            "remaining rows whose orthographic notation is already understood by the "
            "shared SAOL layer, so adjective-specific work can focus on slot assignment."
        ),
    }


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    return analyze_records(read_jsonl(saol_path))


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Adjektivposter: {report['adjective_records']}",
        f"Redan tolkade: {report['already_interpreted_records']}",
        f"Återstår: {report['remaining_records']}",
        f"Återstående som gemensamma lagret kan tokenisera: {report['remaining_tokenizable_by_shared_layer']}",
        f"Återstående med helt strukturellt tolkbar notation: {report['remaining_structured_by_shared_layer']}",
        f"Återstående med valfria formdelar: {report['remaining_with_optional_form_tokens']}",
        "",
        "Valfria formtoken:",
    ]
    for token, count in report["optional_token_counts"].items():
        lines.append(f"  {count:6d}  {token}")
    lines.extend(["", "Strukturellt tolkbara återstående poster:"])
    selected = [row for row in report["records"] if row["shared_structured"]]
    if not selected:
        lines.append("  (inga)")
    for row in selected[:300]:
        lines.append(
            f"  {row['lemma']} (homonr={row['homonym_number'] or '-'}) | "
            f"text={row['text']!r} | tokens={row['tokens']!r}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-audit remaining SAOL14 adjectives with shared notation parsing"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.text.write_text(render_text(report), encoding="utf-8")
    print(f"Adjektivposter: {report['adjective_records']}")
    print(f"Redan tolkade: {report['already_interpreted_records']}")
    print(f"Återstår: {report['remaining_records']}")
    print(
        "Gemensamt strukturellt tolkbara: "
        f"{report['remaining_structured_by_shared_layer']}"
    )
    print(
        "Med valfria formdelar: "
        f"{report['remaining_with_optional_form_tokens']}"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
