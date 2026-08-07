from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .inflect import COMMON_PATTERNS, EXPLICIT_PATTERN_GROUP, generate_entry, normalise_pattern
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-rule-usage.txt")
DEFAULT_JSON = Path("reports/saol14-rule-usage.json")


def classify_rule_path(record: dict[str, Any]) -> str:
    raw = str(record.get("text", "")).strip()
    normalized = normalise_pattern(raw)
    initial = generate_entry(record)
    completed = complete_noun_entry(record, initial)

    if completed is None:
        return "unsupported"
    if initial is None:
        return "noun_completion_from_unsupported"
    if completed != initial:
        return "noun_completion_after_base_generation"
    if initial.pattern_group == EXPLICIT_PATTERN_GROUP:
        return "generic_explicit_parser"
    if normalized in COMMON_PATTERNS:
        return "common_pattern"
    return "other_generated"


def build_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path_counts: Counter[str] = Counter()
    normalized_counts: Counter[str] = Counter()
    raw_counts: Counter[str] = Counter()
    common_counts: Counter[str] = Counter()
    unsupported_counts: Counter[str] = Counter()

    total = 0
    for record in records:
        total += 1
        raw = str(record.get("text", "")).strip()
        normalized = normalise_pattern(raw) or "(none)"
        path = classify_rule_path(record)
        path_counts[path] += 1
        normalized_counts[normalized] += 1
        raw_counts[raw or "(none)"] += 1
        if normalized in COMMON_PATTERNS:
            common_counts[normalized] += 1
        if path == "unsupported":
            unsupported_counts[normalized] += 1

    unused_common_patterns = sorted(set(COMMON_PATTERNS) - set(common_counts))
    rare_common_patterns = {
        pattern: count
        for pattern, count in sorted(common_counts.items(), key=lambda item: (item[1], item[0]))
        if count <= 10
    }

    return {
        "records": total,
        "named_common_patterns": len(COMMON_PATTERNS),
        "rule_path_counts": dict(path_counts.most_common()),
        "common_pattern_counts": dict(common_counts.most_common()),
        "unused_common_patterns": unused_common_patterns,
        "rare_common_patterns": rare_common_patterns,
        "top_unsupported_patterns": dict(unsupported_counts.most_common(50)),
        "top_normalized_patterns": dict(normalized_counts.most_common(100)),
        "top_raw_patterns": dict(raw_counts.most_common(100)),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"SAOL-poster: {report['records']}",
        f"Namngivna grundmönster: {report['named_common_patterns']}",
        "",
        "Kodvägar:",
    ]
    for name, count in report["rule_path_counts"].items():
        lines.append(f"  {count:6d}  {name}")

    lines.extend(["", "Grundmönster:"])
    for pattern, count in report["common_pattern_counts"].items():
        lines.append(f"  {count:6d}  {pattern}")

    lines.extend(["", "Oanvända grundmönster:"])
    unused = report["unused_common_patterns"]
    lines.extend(f"  {pattern}" for pattern in unused)
    if not unused:
        lines.append("  –")

    lines.extend(["", "Sällsynta grundmönster (högst 10 poster):"])
    rare = report["rare_common_patterns"]
    for pattern, count in rare.items():
        lines.append(f"  {count:6d}  {pattern}")
    if not rare:
        lines.append("  –")

    lines.extend(["", "Största ännu ostödda normaliserade mönster:"])
    for pattern, count in report["top_unsupported_patterns"].items():
        lines.append(f"  {count:6d}  {pattern}")

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Count SAOL rule and parser-path usage")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {report['records']}")
    print(f"Grundmönster: {report['named_common_patterns']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
