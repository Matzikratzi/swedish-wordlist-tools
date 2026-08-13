from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .adjective_slots import interpret_simple_adjective_slots
from .jsonl import read_jsonl
from .saol_notation import normalize_notation

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-replace-tail.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-replace-tail.json")

_REPLACEMENT_TOKEN = re.compile(r"(?<!\+)-(?P<tail>[a-zåäöéü]+)")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def _stycke_prefix(record: dict[str, Any], lemma: str) -> str:
    stycke = re.sub(r"<[^>]+>", "", _value(record, "stycke")).casefold()
    if "|" not in stycke:
        return ""
    prefix = "".join(stycke.split("|")[:-1])
    prefix = re.sub(r"^\d+", "", prefix)
    prefix = "".join(char for char in prefix if char.isalpha() or char == "-")
    return prefix if prefix and lemma.startswith(prefix) else ""


def _fallback_replace_tail(lemma: str, tail: str) -> str | None:
    positions = [index for index, char in enumerate(lemma) if char == tail[0]]
    return None if not positions else lemma[: positions[-1]] + tail


def replacement_events(record: dict[str, Any]) -> list[dict[str, str]]:
    lemma = _value(record, "normaliserat_ord").casefold()
    notation = normalize_notation(_value(record, "text"))
    prefix = _stycke_prefix(record, lemma)
    events: list[dict[str, str]] = []

    for match in _REPLACEMENT_TOKEN.finditer(notation):
        tail = match.group("tail")
        if prefix:
            method = "lodstreck"
            result = prefix + tail
        else:
            result = _fallback_replace_tail(lemma, tail)
            method = "fallback" if result is not None else "failed"
        events.append(
            {
                "lemma": lemma,
                "stycke": _value(record, "stycke"),
                "notation": _value(record, "text"),
                "token": "-" + tail,
                "prefix": prefix,
                "method": method,
                "result": result or "",
            }
        )
    return events


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    events: list[dict[str, str]] = []
    interpreted_records = 0
    records_with_replacement = 0

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "ADJ":
            continue
        if interpret_simple_adjective_slots(record) is None:
            continue
        interpreted_records += 1
        row_events = replacement_events(record)
        if row_events:
            records_with_replacement += 1
            events.extend(row_events)

    operation_counts = Counter(event["method"] for event in events)
    record_methods: dict[str, set[str]] = {}
    for event in events:
        key = "\u0000".join((event["lemma"], event["stycke"], event["notation"]))
        record_methods.setdefault(key, set()).add(event["method"])
    record_counts = Counter(
        method
        for methods in record_methods.values()
        for method in methods
    )

    fallback_examples = [event for event in events if event["method"] == "fallback"][:100]
    failed_examples = [event for event in events if event["method"] == "failed"][:100]

    return {
        "interpreted_adjective_records": interpreted_records,
        "records_with_replacement": records_with_replacement,
        "replacement_operations": len(events),
        "operation_counts": dict(operation_counts.most_common()),
        "record_counts": dict(record_counts.most_common()),
        "fallback_examples": fallback_examples,
        "failed_examples": failed_examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Tolkade adjektivposter: {report['interpreted_adjective_records']}",
        f"Poster med -ersättning: {report['records_with_replacement']}",
        f"-ersättningsoperationer: {report['replacement_operations']}",
        "",
        "Operationer per metod:",
    ]
    for method, count in report["operation_counts"].items():
        lines.append(f"  {count:6d}  {method}")

    lines.extend(["", "Berörda poster per metod:"])
    for method, count in report["record_counts"].items():
        lines.append(f"  {count:6d}  {method}")

    if report["fallback_examples"]:
        lines.extend(["", "Fallback-exempel:"])
        for event in report["fallback_examples"]:
            lines.append(
                f"  {event['lemma']} | stycke={event['stycke']!r} | "
                f"{event['token']} -> {event['result']}"
            )

    if report["failed_examples"]:
        lines.extend(["", "Misslyckade exempel:"])
        for event in report["failed_examples"]:
            lines.append(
                f"  {event['lemma']} | stycke={event['stycke']!r} | {event['token']}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Count lodstreck and fallback use for adjective -replacement notation"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-ersättningsoperationer: {report['replacement_operations']}")
    for method, count in report["operation_counts"].items():
        print(f"{method}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
