from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .compare_sources import _saol_upos
from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-ordkl-field-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-ordkl-field-analysis.json")

SUSPECTED_ORDKL_LIMIT = 30


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [str(row.get("ordkl") or "") for row in rows]
    lengths = Counter(len(value) for value in values)
    max_length = max(lengths, default=0)
    at_limit = [
        row for row, value in zip(rows, values)
        if len(value) == SUSPECTED_ORDKL_LIMIT
    ]
    at_max = [row for row, value in zip(rows, values) if len(value) == max_length]
    names = [row for row, value in zip(rows, values) if value.strip().casefold() == "namn"]
    name_raw_upos = Counter(str(row.get("upos") or "") for row in names)
    name_resolved_upos = Counter(_saol_upos(row) for row in names)
    limit_values = Counter(str(row.get("ordkl") or "") for row in at_limit)

    def compact(row: dict[str, Any]) -> dict[str, str]:
        return {
            "lemma": str(row.get("normaliserat_ord") or ""),
            "homonym_number": str(row.get("homonr") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "raw_upos": str(row.get("upos") or ""),
            "resolved_upos": _saol_upos(row),
            "text": str(row.get("text") or ""),
            "record_id": str(row.get("subnr") or row.get("urspr_lopnr") or ""),
        }

    examples_by_limit_value: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in at_limit:
        value = str(row.get("ordkl") or "")
        if len(examples_by_limit_value[value]) < 8:
            examples_by_limit_value[value].append(compact(row))

    ordered_limit_values = sorted(limit_values.items(), key=lambda item: (-item[1], item[0]))
    return {
        "records": len(rows),
        "max_ordkl_length": max_length,
        "length_counts": {str(key): value for key, value in sorted(lengths.items())},
        "suspected_limit": SUSPECTED_ORDKL_LIMIT,
        "ordkl_at_suspected_limit": len(at_limit),
        "unique_ordkl_at_suspected_limit": len(limit_values),
        "limit_value_groups": [
            {
                "ordkl": value,
                "count": count,
                "examples": examples_by_limit_value[value],
            }
            for value, count in ordered_limit_values[:100]
        ],
        "max_length_examples": [compact(row) for row in at_max[:50]],
        "name_records": len(names),
        "name_raw_upos": dict(name_raw_upos.most_common()),
        "name_resolved_upos": dict(name_resolved_upos.most_common()),
        "name_examples": [compact(row) for row in names[:100]],
    }


def render(summary: dict[str, Any]) -> str:
    limit = summary["suspected_limit"]
    lines = [
        "SAOL14: analys av ordkl-fältet",
        "",
        f"Poster: {summary['records']}",
        f"Maxlängd ordkl: {summary['max_ordkl_length']}",
        f"Poster med ordkl-längd exakt {limit}: {summary['ordkl_at_suspected_limit']}",
        f"Unika ordkl-värden med längd {limit}: {summary['unique_ordkl_at_suspected_limit']}",
        "",
        "Längdfördelning:",
    ]
    for length, count in summary["length_counts"].items():
        lines.append(f"  {length:>3}: {count}")

    lines.extend(["", f"ordkl='namn': {summary['name_records']}"])
    lines.append(
        "Rå UPOS för namn: "
        + (
            ", ".join(
                f"{key or '(tomt)'}={value}"
                for key, value in summary["name_raw_upos"].items()
            )
            or "(inga)"
        )
    )
    lines.append(
        "Resolverad SAOL-UPOS för namn: "
        + (
            ", ".join(
                f"{key or '(tomt)'}={value}"
                for key, value in summary["name_resolved_upos"].items()
            )
            or "(inga)"
        )
    )
    for row in summary["name_examples"][:30]:
        lines.append(
            f"  {row['lemma']} ({row['homonym_number']}) | "
            f"raw_upos={row['raw_upos'] or '(tomt)'} | "
            f"resolved_upos={row['resolved_upos'] or '(tomt)'} | text={row['text']}"
        )

    lines.extend(["", f"Vanligaste ordkl-värdena med exakt {limit} tecken:"])
    for group in summary["limit_value_groups"][:50]:
        lines.append(f"  {group['count']:5} | {group['ordkl']}")
        examples = ", ".join(row["lemma"] for row in group["examples"][:8])
        if examples:
            lines.append(f"        Exempel: {examples}")

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

    limit = summary["suspected_limit"]
    print(f"Poster: {summary['records']}")
    print(f"Maxlängd ordkl: {summary['max_ordkl_length']}")
    print(f"ordkl-längd {limit}: {summary['ordkl_at_suspected_limit']}")
    print(f"unika ordkl-värden vid {limit}: {summary['unique_ordkl_at_suspected_limit']}")
    print(f"ordkl='namn': {summary['name_records']}")
    print(
        "Rå UPOS för namn: "
        + ", ".join(
            f"{key or '(tomt)'}={value}"
            for key, value in summary["name_raw_upos"].items()
        )
    )
    print(
        "Resolverad SAOL-UPOS för namn: "
        + ", ".join(
            f"{key or '(tomt)'}={value}"
            for key, value in summary["name_resolved_upos"].items()
        )
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
