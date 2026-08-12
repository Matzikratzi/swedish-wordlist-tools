from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .saol_notation import normalize_notation, tokenize_notation
from .saol_source_policy import is_truncated_inflection_source

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-pronoun-notation.txt")
DEFAULT_JSON = Path("reports/saol14-pronoun-notation.json")


def _text(record: dict[str, Any]) -> str:
    value = record.get("text")
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def _token_kind(token: str) -> str:
    lower = token.casefold().strip("()")
    if token in {",", ";"}:
        return token
    if lower in {"el.", "h", "ibl."}:
        return "ALT"
    if lower.endswith(":"):
        return "EDITORIAL:"
    if lower.endswith(".") and not lower.startswith(("+", "-")):
        return f"LABEL:{lower}"
    if lower == "+":
        return "UNCHANGED"
    if lower.startswith("+"):
        return "APPEND"
    if lower.startswith("-"):
        return "REPLACE"
    return "FORM"


def notation_signature(text: str) -> tuple[str, ...]:
    tokens = tokenize_notation(text)
    if tokens is None:
        return ("<TOKENIZE_FAILED>",)
    return tuple(_token_kind(token) for token in tokens)


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    pronouns = [record for record in records if str(record.get("upos") or "").upper() == "PRON"]
    with_text = [record for record in pronouns if _text(record)]
    signature_counts: Counter[tuple[str, ...]] = Counter()
    signature_examples: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    truncated: list[dict[str, Any]] = []

    for record in with_text:
        text = _text(record)
        signature = notation_signature(text)
        signature_counts[signature] += 1
        if len(signature_examples[signature]) < 8:
            signature_examples[signature].append(
                {
                    "lemma": str(record.get("normaliserat_ord") or ""),
                    "homonr": str(record.get("homonr") or ""),
                    "text": text,
                    "ordkl": str(record.get("ordkl") or ""),
                    "stycke": str(record.get("stycke") or ""),
                }
            )
        if is_truncated_inflection_source(record):
            truncated.append(
                {
                    "lemma": str(record.get("normaliserat_ord") or ""),
                    "homonr": str(record.get("homonr") or ""),
                    "length": len(text),
                    "text": text,
                    "ordkl": str(record.get("ordkl") or ""),
                }
            )

    signatures = []
    for signature, count in signature_counts.most_common():
        signatures.append(
            {
                "count": count,
                "signature": list(signature),
                "examples": signature_examples[signature],
            }
        )

    return {
        "pronoun_records": len(pronouns),
        "with_text": len(with_text),
        "without_text": len(pronouns) - len(with_text),
        "truncated_records": len(truncated),
        "distinct_signatures": len(signatures),
        "signatures": signatures,
        "truncated": sorted(truncated, key=lambda row: (row["lemma"], row["homonr"])),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14 PRON: notationsaudit före shared-slotmigrering",
        "",
        f"PRON-poster: {report['pronoun_records']}",
        f"Med textfält: {report['with_text']}",
        f"Utan textfält: {report['without_text']}",
        f"Trunkerade 49/50-rader: {report['truncated_records']}",
        f"Distinkta token-signaturer: {report['distinct_signatures']}",
        "",
        "Signaturer:",
    ]
    for index, group in enumerate(report["signatures"], start=1):
        lines.append(f"\n{index}. antal={group['count']} | {' '.join(group['signature'])}")
        for example in group["examples"]:
            lines.append(
                f"   {example['lemma']} ({example['homonr']}) | text={example['text']!r} | ordkl={example['ordkl']!r}"
            )

    lines.extend(["", "Trunkerade rader:"])
    if not report["truncated"]:
        lines.append("  (inga)")
    else:
        for row in report["truncated"]:
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) | len={row['length']} | text={row['text']!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SAOL14 pronoun notation structures")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(list(read_jsonl(args.saol)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"PRON-poster: {report['pronoun_records']}")
    print(f"Med textfält: {report['with_text']}")
    print(f"Trunkerade: {report['truncated_records']}")
    print(f"Distinkta token-signaturer: {report['distinct_signatures']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
