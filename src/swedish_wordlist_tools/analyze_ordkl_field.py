from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-ordkl-field-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-ordkl-field-analysis.json")


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [str(row.get("ordkl") or "") for row in rows]
    lengths = Counter(len(value) for value in values)
    max_length = max(lengths, default=0)
    at_50 = [row for row, value in zip(rows, values) if len(value) == 50]
    at_max = [row for row, value in zip(rows, values) if len(value) == max_length]
    names = [row for row, value in zip(rows, values) if value.strip().casefold() == "namn"]
    name_upos = Counter(str(row.get("upos") or "") for row in names)

    def compact(row: dict[str, Any]) -> dict[str, str]:
        return {
            "lemma": str(row.get("normaliserat_ord") or ""),
            "homonym_number": str(row.get("homonr") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "upos": str(row.get("upos") or ""),
            "text": str(row.get("text") or ""),
            "record_id": str(row.get("subnr") or row.get("urspr_lopnr") or ""),
        }

    return {
        "records": len(rows),
        "max_ordkl_length": max_length,
        "length_counts": {str(key): value for key, value in sorted(lengths.items())},
        "ordkl_length_50": len(at_50),
        "length_50_examples": [compact(row) for row in at_50[:50]],
        "max_length_examples": [compact(row) for row in at_max[:50]],
        "name_records": len(names),
        "name_upos": dict(name_upos.most_common()),
        "name_examples": [compact(row) for row in names[:100]],
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: analys av ordkl-fältet",
        "",
        f"Poster: {summary['records']}",
        f"Maxlängd ordkl: {summary['max_ordkl_length']}",
        f"Poster med ordkl-längd exakt 50: {summary['ordkl_length_50']}",
        "",
        "Längdfördelning:",
    ]
    for length, count in summary["length_counts"].items():
        lines.append(f"  {length:>3}: {count}")

    lines.extend(["", f"ordkl='namn': {summary['name_records']}"])
    lines.append(
        "UPOS för namn: "
        + (", ".join(f"{key or '(tomt)'}={value}" for key, value in summary["name_upos"].items()) or "(inga)")
    )
    for row in summary["name_examples"][:30]:
        lines.append(
            f"  {row['lemma']} ({row['homonym_number']}) | upos={row['upos'] or '(tomt)'} | text={row['text']}"
        )

    if summary["ordkl_length_50"]:
        lines.extend(["", "Exempel med ordkl-längd 50:"])
        for row in summary["length_50_examples"][:30]:
            lines.append(f"  {row['lemma']} | {row['ordkl']}")
    else:
        lines.extend(["", "Inga ordkl-värden är exakt 50 tecken långa."])

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = build_summary(list(read_jsonl(args.input)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Poster: {summary['records']}")
    print(f"Maxlängd ordkl: {summary['max_ordkl_length']}")
    print(f"ordkl-längd 50: {summary['ordkl_length_50']}")
    print(f"ordkl='namn': {summary['name_records']}")
    print("UPOS för namn: " + ", ".join(f"{key or '(tomt)'}={value}" for key, value in summary["name_upos"].items()))
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
