from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_REPORT = Path("reports/saol14-inspection.json")
NULL_TEXT_VALUES = {"", "(null)"}


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


def normalise_text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = display_value(value)
    return None if rendered in NULL_TEXT_VALUES else rendered


def record_matches(
    record: dict[str, Any],
    *,
    text_filter: str | None,
    upos_filter: str | None,
) -> bool:
    if text_filter is not None and normalise_text(record.get("text")) != text_filter:
        return False
    if upos_filter is not None and display_value(record.get("upos", "")) != upos_filter:
        return False
    return True


def inspect_file(
    path: Path,
    examples_per_value: int = 3,
    *,
    text_filter: str | None = None,
    upos_filter: str | None = None,
) -> dict[str, Any]:
    field_presence: Counter[str] = Counter()
    field_types: dict[str, Counter[str]] = defaultdict(Counter)
    counters = {
        "ordkl": Counter(),
        "upos": Counter(),
        "text": Counter(),
    }
    examples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    source_records = 0
    records = 0
    missing_text = 0

    for record in read_jsonl(path):
        source_records += 1
        if not record_matches(record, text_filter=text_filter, upos_filter=upos_filter):
            continue

        records += 1
        headword = display_value(record.get("normaliserat_ord", record.get("ord", "")))

        for field, value in record.items():
            field_presence[field] += 1
            field_types[field][value_type(value)] += 1

        for field in ("ordkl", "upos"):
            value = display_value(record.get(field, ""))
            if value:
                counters[field][value] += 1
                if len(examples[field][value]) < examples_per_value:
                    examples[field][value].append(headword)

        text = normalise_text(record.get("text"))
        if text is None:
            missing_text += 1
        else:
            counters["text"][text] += 1
            if len(examples["text"][text]) < examples_per_value:
                examples["text"][text].append(headword)

    def top(field: str, limit: int = 200) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count, "examples": examples[field][value]}
            for value, count in counters[field].most_common(limit)
        ]

    return {
        "source": str(path),
        "source_records": source_records,
        "records": records,
        "filters": {"text": text_filter, "upos": upos_filter},
        "fields": {
            field: {
                "present": field_presence[field],
                "missing": records - field_presence[field],
                "types": dict(field_types[field]),
            }
            for field in sorted(field_presence)
        },
        "top_values": {field: top(field) for field in ("ordkl", "upos", "text")},
        "unique_counts": {field: len(counters[field]) for field in ("ordkl", "upos", "text")},
        "missing_values": {"text": missing_text},
    }


def print_value_table(title: str, values: list[dict[str, Any]], limit: int) -> None:
    print(title)
    for item in values[:limit]:
        print(f"  {item['count']:>7}  {item['value']}")
        if item["examples"]:
            print(f"           Exempel: {', '.join(item['examples'])}")


def print_summary(report: dict[str, Any], *, list_limit: int = 20) -> None:
    print(f"Poster i källfilen: {report['source_records']}")
    print(f"Matchande poster: {report['records']}")

    active_filters = {name: value for name, value in report["filters"].items() if value is not None}
    if active_filters:
        print("Filter:")
        for name, value in active_filters.items():
            print(f"  {name}: {value}")

    print("Fält:")
    for field, info in report["fields"].items():
        types = ", ".join(f"{name}={count}" for name, count in info["types"].items())
        print(f"  {field}: {info['present']} poster ({types})")

    print("Unika värden:")
    for field, count in report["unique_counts"].items():
        print(f"  {field}: {count}")

    print("Saknade böjningsvärden:")
    print(f"  text: {report['missing_values']['text']}")
    print_value_table("UPOS:", report["top_values"]["upos"], list_limit)
    print_value_table("Vanligaste textvärden:", report["top_values"]["text"], list_limit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the SAOL 14 facsimile JSONL dataset")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--text", dest="text_filter", help='Only include records with this exact text value, for example "+en +er"')
    parser.add_argument("--upos", dest="upos_filter", help='Only include records with this UPOS value, for example "NOUN"')
    parser.add_argument("--examples", type=int, default=3, help="Number of example headwords stored for each value")
    parser.add_argument("--list-limit", type=int, default=20, help="Number of values printed in each summary table")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.examples < 0:
        raise SystemExit("--examples must be zero or greater")
    if args.list_limit < 0:
        raise SystemExit("--list-limit must be zero or greater")

    report = inspect_file(
        args.input,
        examples_per_value=args.examples,
        text_filter=args.text_filter,
        upos_filter=args.upos_filter,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(report, list_limit=args.list_limit)
    print(f"Rapport: {args.output}")


if __name__ == "__main__":
    main()
