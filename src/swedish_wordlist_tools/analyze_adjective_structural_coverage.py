from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .jsonl import read_jsonl

DEFAULT_ARTIFACT = Path("reports/saol14-adjective-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-structural-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-structural-coverage.json")
STRUCTURAL_PREFIX = "structural_"
SHARED_PREFIX = "shared_"
LEGACY_EXAMPLE_LIMIT = 5


def build_summary(path: Path = DEFAULT_ARTIFACT) -> dict[str, object]:
    rows = list(read_jsonl(path))
    rule_counts = Counter(str(row.get("rule") or "(none)") for row in rows)
    shared = sum(count for rule, count in rule_counts.items() if rule.startswith(SHARED_PREFIX))
    structural = sum(
        count for rule, count in rule_counts.items() if rule.startswith(STRUCTURAL_PREFIX)
    )
    no_inflection = rule_counts.get("lemma_only_no_inflection_text", 0)
    clean_room = shared + structural
    legacy = len(rows) - clean_room - no_inflection

    legacy_examples: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        rule = str(row.get("rule") or "(none)")
        if (
            rule.startswith(STRUCTURAL_PREFIX)
            or rule.startswith(SHARED_PREFIX)
            or rule == "lemma_only_no_inflection_text"
        ):
            continue
        if len(legacy_examples[rule]) >= LEGACY_EXAMPLE_LIMIT:
            continue
        source = dict(row.get("source_record") or {})
        legacy_examples[rule].append(
            {
                "lemma": row.get("lemma"),
                "homonym_number": row.get("homonym_number"),
                "text": source.get("text"),
                "ordkl": source.get("ordkl"),
                "stycke": source.get("stycke"),
                "subnr": source.get("subnr"),
                "forms": [form.get("written_form") for form in row.get("forms", [])],
            }
        )

    return {
        "records": len(rows),
        "shared_records": shared,
        "structural_records": structural,
        "clean_room_records": clean_room,
        "no_inflection_text_records": no_inflection,
        "legacy_records": legacy,
        "rule_counts": dict(rule_counts.most_common()),
        "legacy_examples": dict(legacy_examples),
    }


def render_text(summary: dict[str, object]) -> str:
    lines = [
        "SAOL14 ADJ: clean-room-täckning",
        "",
        f"Genererade poster: {summary['records']}",
        f"Shared-motor: {summary['shared_records']}",
        f"Övriga strukturella vägar: {summary['structural_records']}",
        f"Clean-room totalt: {summary['clean_room_records']}",
        f"Utan böjningstext: {summary['no_inflection_text_records']}",
        f"Legacy: {summary['legacy_records']}",
        "",
        "Regler:",
    ]
    for rule, count in dict(summary["rule_counts"]).items():
        lines.append(f"  {count:6d}  {rule}")

    examples = dict(summary.get("legacy_examples") or {})
    if examples:
        lines.extend(("", "Kvarvarande legacy-vägar – exempel:"))
        for rule, rows in examples.items():
            lines.append("")
            lines.append(f"{rule}:")
            for row in rows:
                lines.append(
                    "  "
                    + f"{row.get('lemma')} ({row.get('homonym_number')}) | "
                    + f"text={row.get('text')!r} | stycke={row.get('stycke')!r} | "
                    + f"forms={row.get('forms')}"
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure how much of the ADJ artifact uses shared/structural clean-room parsing"
    )
    parser.add_argument("artifact", nargs="?", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = build_summary(args.artifact)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(summary), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(render_text(summary), end="")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
