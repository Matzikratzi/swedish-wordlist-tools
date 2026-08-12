from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_source_policy import is_truncated_inflection_source, raw_inflection_text

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-pos-inventory.txt")
DEFAULT_JSON = Path("reports/saol14-pos-inventory.json")

# These word classes now use the shared/clean-room SAOL notation model for
# their inflection interpretation.  Other UPOS values are inventory targets;
# this report deliberately does not assume that a non-empty text field means
# that a new inflection parser is needed.
SHARED_INFLECTION_UPOS = frozenset({"NOUN", "ADJ", "VERB"})


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    by_upos: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    ordkl_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        total += 1
        upos = _value(record, "upos").upper() or "(EMPTY)"
        text = raw_inflection_text(record)
        has_text = bool(text.strip()) and text.strip() != "(null)"

        stats = by_upos[upos]
        stats["records"] += 1
        if has_text:
            stats["with_text"] += 1
            if is_truncated_inflection_source(record):
                stats["truncated"] += 1
        else:
            stats["without_text"] += 1

        ordkl = _value(record, "ordkl")
        if ordkl:
            ordkl_counts[upos][ordkl] += 1

        if has_text and len(examples[upos]) < 8:
            examples[upos].append(
                {
                    "lemma": _value(record, "normaliserat_ord"),
                    "homonr": _value(record, "homonr"),
                    "text": text,
                    "ordkl": ordkl,
                }
            )

    rows: list[dict[str, Any]] = []
    for upos, stats in by_upos.items():
        rows.append(
            {
                "upos": upos,
                "status": "shared_inflection" if upos in SHARED_INFLECTION_UPOS else "not_yet_audited",
                "records": stats["records"],
                "with_text": stats["with_text"],
                "without_text": stats["without_text"],
                "truncated": stats["truncated"],
                "top_ordkl": [
                    {"ordkl": ordkl, "count": count}
                    for ordkl, count in ordkl_counts[upos].most_common(8)
                ],
                "examples_with_text": examples[upos],
            }
        )

    rows.sort(key=lambda row: (-row["with_text"], -row["records"], row["upos"]))
    remaining = [row for row in rows if row["status"] != "shared_inflection"]
    return {
        "records": total,
        "shared_inflection_upos": sorted(SHARED_INFLECTION_UPOS),
        "upos_classes": len(rows),
        "remaining_upos_classes": len(remaining),
        "remaining_records": sum(row["records"] for row in remaining),
        "remaining_records_with_text": sum(row["with_text"] for row in remaining),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: inventering av ordklasser efter NOUN/ADJ/VERB shared-migrering",
        "",
        f"Poster totalt: {report['records']}",
        f"UPOS-klasser: {report['upos_classes']}",
        "Shared böjning: " + ", ".join(report["shared_inflection_upos"]),
        f"Kvarvarande UPOS-klasser att auditera: {report['remaining_upos_classes']}",
        f"Kvarvarande poster: {report['remaining_records']}",
        f"Kvarvarande poster med textfält: {report['remaining_records_with_text']}",
        "",
        "UPOS                         poster    text   utan text  trunk.  status",
    ]
    for row in report["rows"]:
        lines.append(
            f"{row['upos']:<28} {row['records']:>7} {row['with_text']:>7} "
            f"{row['without_text']:>10} {row['truncated']:>7}  {row['status']}"
        )

    lines.extend(["", "Kvarvarande klasser – exempel på textfält:"])
    for row in report["rows"]:
        if row["status"] == "shared_inflection" or not row["with_text"]:
            continue
        lines.append(f"\n[{row['upos']}] poster={row['records']} text={row['with_text']}")
        for example in row["examples_with_text"]:
            lines.append(
                f"  {example['lemma']} ({example['homonr']}) | text={example['text']!r} "
                f"| ordkl={example['ordkl']!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL14 UPOS classes and inflection-text volume")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Poster totalt: {report['records']}")
    print("Shared böjning: " + ", ".join(report["shared_inflection_upos"]))
    print(f"Kvarvarande UPOS-klasser: {report['remaining_upos_classes']}")
    print(f"Kvarvarande poster med textfält: {report['remaining_records_with_text']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
