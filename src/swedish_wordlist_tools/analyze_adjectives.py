from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .adjective_slots import interpret_simple_adjective_slots
from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjectives.txt")
DEFAULT_JSON = Path("reports/saol14-adjectives.json")
HARD_CAP = 50


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _pattern(text: str) -> str:
    return " ".join(text.split()) if text else "(none)"


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "ADJ"
    ]
    pattern_counts: Counter[str] = Counter()
    remaining_pattern_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    length_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for record in records:
        text = _value(record, "text")
        stycke = _value(record, "stycke")
        pattern = _pattern(text)
        slots = interpret_simple_adjective_slots(record)
        pattern_counts[pattern] += 1
        if slots is None:
            remaining_pattern_counts[pattern] += 1
        else:
            rule_counts[slots.rule] += 1
        length_counts["at_hard_cap" if len(text) == HARD_CAP else "below_hard_cap"] += 1
        rows.append({
            "lemma": _value(record, "normaliserat_ord"),
            "homonr": _value(record, "homonr"),
            "text": text or None,
            "text_length": len(text),
            "at_hard_cap": len(text) == HARD_CAP,
            "has_bar": "|" in stycke,
            "stycke": stycke,
            "ordkl": _value(record, "ordkl"),
            "interpreted": slots is not None,
            "rule": slots.rule if slots else None,
            "forms": list(slots.written_forms()) if slots else [],
            "source": _value(record, "source"),
        })

    interpreted = sum(1 for row in rows if row["interpreted"])
    rows.sort(key=lambda row: (not row["at_hard_cap"], row["interpreted"], row["lemma"], row["homonr"]))
    return {
        "adjective_records": len(records),
        "with_text": sum(1 for row in rows if row["text"]),
        "without_text": sum(1 for row in rows if not row["text"]),
        "interpreted_simple_records": interpreted,
        "interpreted_simple_percent": round(100 * interpreted / len(records), 2) if records else 0.0,
        "remaining_records": len(records) - interpreted,
        "at_hard_cap": length_counts["at_hard_cap"],
        "with_bar": sum(1 for row in rows if row["has_bar"]),
        "unique_raw_patterns": len(pattern_counts),
        "rule_counts": dict(rule_counts.most_common()),
        "top_raw_patterns": pattern_counts.most_common(100),
        "top_remaining_patterns": remaining_pattern_counts.most_common(100),
        "records": rows,
        "note": (
            "The simple parser handles only exact +t +a, n. +, +a, +tt +a and +t +ma rows. "
            "No adjective forms are exported by this command."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Adjektivposter: {report['adjective_records']}",
        f"Med text: {report['with_text']}",
        f"Utan text: {report['without_text']}",
        f"Enkelt tolkade: {report['interpreted_simple_records']} "
        f"({report['interpreted_simple_percent']:.2f} %)",
        f"Återstår: {report['remaining_records']}",
        f"Vid 50-teckensgränsen: {report['at_hard_cap']}",
        f"Med lodstreck i stycke: {report['with_bar']}",
        f"Unika råa textmönster: {report['unique_raw_patterns']}",
        "",
        "Tolkade regler:",
    ]
    for rule, count in report["rule_counts"].items():
        lines.append(f"  {count:6d}  {rule}")
    lines.extend(["", "Vanligaste återstående råa textmönster:"])
    for pattern, count in report["top_remaining_patterns"]:
        lines.append(f"  {count:6d}  {pattern}")
    lines.extend(["", "Poster vid 50-teckensgränsen:"])
    capped = [row for row in report["records"] if row["at_hard_cap"]]
    if not capped:
        lines.append("  (inga)")
    for row in capped[:300]:
        lines.append(
            f"  {row['lemma']} (homonr={row['homonr'] or '-'}) | "
            f"text={row['text']!r} | stycke={row['stycke']!r}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory and conservatively parse SAOL14 adjective rows")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Adjektivposter: {report['adjective_records']}")
    print(
        f"Enkelt tolkade: {report['interpreted_simple_records']} "
        f"({report['interpreted_simple_percent']:.2f} %)"
    )
    print(f"Återstår: {report['remaining_records']}")
    print(f"Vid 50-teckensgränsen: {report['at_hard_cap']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
