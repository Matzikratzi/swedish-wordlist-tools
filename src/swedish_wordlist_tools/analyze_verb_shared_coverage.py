from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analyze_verb_notation_inventory import DEFAULT_SAOL
from .jsonl import read_jsonl
from .saol_notation import split_alternative_branches
from .saol_source_policy import inflection_text, is_truncated_inflection_source
from .verb_shared_slot_interpreter import (
    interpret_basic_verb_sequence,
    interpret_verb_sequence,
    is_structurally_uninflected_verb,
)

DEFAULT_TEXT = Path("reports/saol14-verb-shared-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-verb-shared-coverage.json")


def classify_branch(record: dict[str, Any], text: str) -> str:
    if is_truncated_inflection_source(record):
        return "truncated_not_yet_shared"
    if is_structurally_uninflected_verb(text):
        return "structural_uninflected"
    if interpret_basic_verb_sequence(text) is not None:
        return "shared_basic_preterite_supine"
    if interpret_verb_sequence(text) is not None:
        return "shared_rich_verb_slots"
    return "remaining_structure"


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    verb_records = 0
    without_inflection_text = 0
    truncated_records = 0
    branch_count = 0
    path_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for record in records:
        if str(record.get("upos") or "").upper() != "VERB":
            continue
        verb_records += 1
        if is_truncated_inflection_source(record):
            truncated_records += 1

        pattern = inflection_text(record)
        if pattern is None:
            without_inflection_text += 1
            continue
        branches = split_alternative_branches(pattern)
        for index, branch in enumerate(branches):
            branch_count += 1
            path = classify_branch(record, branch.text)
            path_counts[path] += 1
            if len(examples[path]) < 30:
                examples[path].append(
                    {
                        "lemma": str(record.get("normaliserat_ord") or ""),
                        "homonym_number": str(record.get("homonr") or ""),
                        "branch": str(index + 1),
                        "text": branch.text,
                        "source_text": str(record.get("text") or ""),
                    }
                )

    shared = (
        path_counts.get("shared_basic_preterite_supine", 0)
        + path_counts.get("shared_rich_verb_slots", 0)
    )
    clean_room = shared + path_counts.get("structural_uninflected", 0)
    return {
        "verb_records": verb_records,
        "without_inflection_text": without_inflection_text,
        "truncated_records": truncated_records,
        "branches": branch_count,
        "path_counts": dict(path_counts.most_common()),
        "shared_branches": shared,
        "shared_branch_percent": round(100.0 * shared / branch_count, 2) if branch_count else 0.0,
        "clean_room_branches": clean_room,
        "clean_room_branch_percent": round(100.0 * clean_room / branch_count, 2) if branch_count else 0.0,
        "examples": dict(examples),
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 VERB: shared-täckning",
        "",
        "Shared-motorn tolkar atomärt positionsbundna och explicit etiketterade",
        "verbslots, inklusive defekta paradigm där normala former saknas.",
        "'ingen böjning' redovisas separat som strukturellt löst. Trunkerade",
        "rader hålls fortfarande separat tills prefix-tolkningen kopplas in.",
        "",
        f"VERB-poster: {summary['verb_records']}",
        f"Utan böjningstext: {summary['without_inflection_text']}",
        f"Trunkerade poster: {summary['truncated_records']}",
        f"Böjningsbrancher: {summary['branches']}",
        f"Shared brancher totalt: {summary['shared_branches']} ({summary['shared_branch_percent']:.2f} %)",
        f"Clean-room brancher totalt: {summary['clean_room_branches']} ({summary['clean_room_branch_percent']:.2f} %)",
        "",
        "Vägar:",
    ]
    for path, count in summary["path_counts"].items():
        lines.append(f"  {count:7d}  {path}")

    for path in ("truncated_not_yet_shared", "remaining_structure"):
        rows = summary["examples"].get(path, [])
        lines.extend(("", f"{path} – exempel:"))
        if not rows:
            lines.append("  (inga)")
        for row in rows[:20]:
            hom = f" ({row['homonym_number']})" if row["homonym_number"] else ""
            lines.append(f"  {row['lemma']}{hom} | branch {row['branch']} | text={row['text']!r}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"VERB-poster: {summary['verb_records']}")
    print(f"Utan böjningstext: {summary['without_inflection_text']}")
    print(f"Trunkerade poster: {summary['truncated_records']}")
    print(f"Böjningsbrancher: {summary['branches']}")
    print(f"Shared brancher totalt: {summary['shared_branches']} ({summary['shared_branch_percent']:.2f} %)")
    print(f"Clean-room brancher totalt: {summary['clean_room_branches']} ({summary['clean_room_branch_percent']:.2f} %)")
    for path, count in summary["path_counts"].items():
        print(f"{path}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
