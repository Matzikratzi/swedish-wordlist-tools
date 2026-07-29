from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_REPORT = Path("reports/saol14-inspection.json")


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def display_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def inspect_file(path: Path, examples_per_value: int = 3) -> dict[str, Any]:
    field_presence: Counter[str] = Counter()
    field_types: dict[str, Counter[str]] = defaultdict(Counter)
    ordklass: Counter[str] = Counter()
    morfosyntax: Counter[str] = Counter()
    text_values: Counter[str] = Counter()
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    records = 0

    for record in read_jsonl(path):
        records += 1
        headword = str(record.get("ingångsord", record.get("ord", "")))
        for field, value in record.items():
            field_presence[field] += 1
            field_types[field][value_type(value)] += 1
            rendered = display_value(value)
            if rendered and len(examples[field][rendered]) < examples_per_value:
                examples[field][rendered].append(headword)

        for field, counter in (
            ("ordklass", ordklass),
            ("morfosyntax", morfosyntax),
            ("text", text_values),
        ):
            value = record.get(field)
            if value not in (None, "", []):
                counter[display_value(value)] += 1

    def top(counter: Counter[str], limit: int = 200) -> list[dict[str, Any]]:
        return [{"value": value, "count": count} for value, count in counter.most_common(limit)]

    return {
        "source": str(path),
        "records": records,
        "fields": {
            field: {
                "present": field_presence[field],
                "missing": records - field_presence[field],
                "types": dict(field_types[field]),
            }
            for field in sorted(field_presence)
        },
        "top_values": {
            "ordklass": top(ordklass),
            "morfosyntax": top(morfosyntax),
            "text": top(text_values),
        },
        "unique_counts": {
            "ordklass": len(ordklass),
            "morfosyntax": len(morfosyntax),
            "text": len(text_values),
        },
    }


def print_summary(report: dict[str, Any]) -> None:
    print(f"Poster: {report['records']}")
    print("Fält:")
    for field, info in report["fields"].items():
        types = ", ".join(f"{name}={count}" for name, count in info["types"].items())
        print(f"  {field}: {info['present']} poster ({types})")
    print("Unika värden:")
    for field, count in report["unique_counts"].items():
        print(f"  {field}: {count}")
    print("Vanligaste textvärden:")
    for item in report["top_values"]["text"][:20]:
        print(f"  {item['count']:>7}  {item['value']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect SAOL 14 JSONL structure")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = inspect_file(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print_summary(report)
    print(f"Rapport: {args.output}")


if __name__ == "__main__":
    main()
