from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-comparison.jsonl")
DEFAULT_REPORT = Path("reports/saol14-noun-semantic-groups.txt")
DEFAULT_JSON = Path("reports/saol14-noun-semantic-groups.json")


def _notation_key(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or "(null)"


def _row_change_types(row: dict[str, Any]) -> tuple[str, ...]:
    reasons = {
        str(reason)
        for reason in row.get("change_reasons", {}).values()
        if reason
    }
    return tuple(sorted(reasons)) or ("no_added_form_reason",)


def _semantic_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("semantic_removed_forms")
    ]


def build_analysis(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    semantic = _semantic_rows(rows)
    notation_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    change_type_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unsupported_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in semantic:
        notation_groups[_notation_key(row.get("notation"))].append(row)
        for reason in _row_change_types(row):
            change_type_groups[reason].append(row)

    for row in rows:
        if row.get("status") == "unsupported":
            unsupported_groups[_notation_key(row.get("notation"))].append(row)

    def summarise(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key, grouped_rows in groups.items():
            examples = sorted(
                grouped_rows,
                key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("record_id", ""))),
            )[:8]
            result.append({
                "key": key,
                "count": len(grouped_rows),
                "examples": [
                    {
                        "lemma": str(row.get("lemma", "")),
                        "stycke": str(row.get("stycke", "")),
                        "added_forms": list(row.get("added_forms", [])),
                        "semantic_removed_forms": list(row.get("semantic_removed_forms", [])),
                    }
                    for row in examples
                ],
            })
        return sorted(result, key=lambda group: (-group["count"], group["key"].casefold()))

    reason_counts = Counter(
        reason
        for row in semantic
        for reason in _row_change_types(row)
    )
    return {
        "semantic_rows": len(semantic),
        "semantic_unique_removed_forms": len({
            str(form).casefold()
            for row in semantic
            for form in row.get("semantic_removed_forms", [])
        }),
        "notation_group_count": len(notation_groups),
        "change_type_counts": dict(sorted(reason_counts.items())),
        "notation_groups": summarise(notation_groups),
        "change_type_groups": summarise(change_type_groups),
        "unsupported_groups": summarise(unsupported_groups),
    }


def render_analysis(analysis: dict[str, Any]) -> str:
    lines = [
        f"Semantiska poster: {analysis['semantic_rows']}",
        f"Unika semantiskt borttagna former: {analysis['semantic_unique_removed_forms']}",
        f"Notationsgrupper: {analysis['notation_group_count']}",
        "Ändringstyper: " + ", ".join(
            f"{key}={value}" for key, value in analysis["change_type_counts"].items()
        ),
    ]

    for heading, groups in (
        ("Grupperade efter notation", analysis["notation_groups"]),
        ("Grupperade efter ändringstyp", analysis["change_type_groups"]),
        ("Unsupported grupperade efter notation", analysis["unsupported_groups"]),
    ):
        lines.extend(["", heading + ":"])
        for index, group in enumerate(groups, start=1):
            lines.extend([
                "",
                f"=== Grupp {index}: {group['count']} poster ===",
                str(group["key"]),
            ])
            for example in group["examples"]:
                added = ", ".join(example["added_forms"]) or "-"
                removed = ", ".join(example["semantic_removed_forms"]) or "-"
                lines.append(
                    f"  {example['lemma']} | stycke={example['stycke']} | "
                    f"tillagt={added} | semantiskt borttaget={removed}"
                )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Group remaining noun semantic differences by SAOL notation and change type"
    )
    parser.add_argument("comparison", nargs="?", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = build_analysis(read_jsonl(args.comparison))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_analysis(analysis), encoding="utf-8")
    args.json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Semantiska poster: {analysis['semantic_rows']}")
    print(f"Notationsgrupper: {analysis['notation_group_count']}")
    print(f"Rapport: {args.report}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
