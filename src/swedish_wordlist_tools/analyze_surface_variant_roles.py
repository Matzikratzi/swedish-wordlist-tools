from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-surface-variant-roles.txt")
DEFAULT_JSON = Path("reports/saol14-surface-variant-roles.json")

_NULL = {"", "(null)", "null"}
# Conservative: every content token must be structural/relative SAOL notation.
# Explicit written lexical forms such as ankaret/ankaren therefore do not pass.
_RELATIVE_TOKEN = re.compile(
    r"^(?:\+[^\s;,]*|\[[^\]]+\]|_|el\.|pl\.|best\.|n\.|sing\.|obest\.|vard\.)$",
    re.IGNORECASE,
)


def _is_null_text(value: object) -> bool:
    return str(value or "").strip().casefold() in _NULL


def _tokens(text: str) -> tuple[str, ...]:
    # punctuation only separates SAOL notation clauses here
    return tuple(part for part in re.split(r"\s+", text.replace(";", " ").replace(",", " ").strip()) if part)


def is_pure_relative_notation(value: object) -> bool:
    text = str(value or "").strip()
    if _is_null_text(text):
        return False
    tokens = _tokens(text)
    return bool(tokens) and any(token.startswith("+") for token in tokens) and all(
        _RELATIVE_TOKEN.fullmatch(token) is not None for token in tokens
    )


def _role(record: dict[str, Any]) -> str:
    ordkl = str(record.get("ordkl") or "").strip().casefold()
    text = record.get("text")
    resolved = _saol_upos(record)
    if ordkl.startswith("(hv)") and _is_null_text(text):
        return "cross_reference"
    if resolved == "NOUN" and is_pure_relative_notation(text):
        return "noun_relative_paradigm_candidate"
    if resolved == "NOUN" and not _is_null_text(text):
        return "noun_lexical_or_complex_paradigm"
    if _is_null_text(text):
        return "other_without_text"
    return "other_with_text"


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    for record in records:
        normalized = clean_saol_word(record.get("normaliserat_ord"))
        written = clean_saol_word(record.get("ord"))
        if not normalized or not written or normalized == written:
            continue
        role = _role(record)
        row = {
            "normaliserat_ord": normalized,
            "ord": written,
            "role": role,
            "homonr": str(record.get("homonr") or ""),
            "record_id": str(record.get("subnr") or record.get("urspr_lopnr") or ""),
            "resolved_upos": _saol_upos(record),
            "raw_upos": str(record.get("upos") or ""),
            "ordkl": str(record.get("ordkl") or ""),
            "text": str(record.get("text") or ""),
            "stycke": str(record.get("stycke") or ""),
        }
        rows.append(row)
        role_counts[role] += 1

    rows.sort(key=lambda row: (row["role"], row["normaliserat_ord"].casefold(), row["ord"].casefold(), row["homonr"]))
    examples: dict[str, list[dict[str, Any]]] = {}
    for role in role_counts:
        examples[role] = [row for row in rows if row["role"] == role][:100]
    return {"records": len(rows), "role_counts": dict(role_counts.most_common()), "examples": examples, "rows": rows}


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: roller för ord != normaliserat_ord",
        "",
        "Rapporten skiljer konservativt mellan hänvisningar, substantivrader med",
        "ett rent relativt +-paradigm och rader med lexikalt/komplext paradigm.",
        "Den fattar ännu inget beslut om vilka ord-varianter som ska genereras.",
        "",
        f"Poster: {summary['records']}",
        "Roller: " + ", ".join(f"{key}={value}" for key, value in summary["role_counts"].items()),
    ]
    for role, rows in summary["examples"].items():
        lines.extend(["", f"Exempel: {role}"])
        for row in rows:
            lines.append(
                f"  {row['normaliserat_ord']} -> {row['ord']}"
                f" | homonr={row['homonr']} | upos={row['resolved_upos']}"
                f" | ordkl={row['ordkl']} | text={row['text']} | stycke={row['stycke']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print("Roller: " + ", ".join(f"{key}={value}" for key, value in summary["role_counts"].items()))
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
