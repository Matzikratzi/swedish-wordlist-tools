from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .generate_noun_forms import DEFAULT_SAOL
from .jsonl import read_jsonl
from .noun_truncated_shared import assign_truncated_noun_branch
from .saol_noun_variants import prepare_noun_variant_records
from .saol_row_interpreter import (
    _assign_labelled_noun_slots_shared,
    _assign_unlabelled_noun_atoms_shared,
    _clean_notation_structure,
    _is_uninflected_branch,
)
from .saol_notation import split_alternative_branches
from .saol_source_policy import inflection_text, is_truncated_inflection_source

DEFAULT_TEXT = Path("reports/saol14-noun-shared-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-noun-shared-coverage.json")


def branch_path(record: dict[str, Any], tokens: tuple[str, ...]) -> str:
    """Classify one already-tokenized noun branch by its current assignment path."""

    if _is_uninflected_branch(tokens):
        return "structural_uninflected"
    if _assign_labelled_noun_slots_shared(tokens) is not None:
        return "shared_labelled"
    if _assign_unlabelled_noun_atoms_shared(record, tokens) is not None:
        return "shared_unlabelled_atoms"
    if is_truncated_inflection_source(record) and assign_truncated_noun_branch(record, tokens) is not None:
        return "shared_truncated_partial"
    return "legacy_fallback"


def fallback_reason(record: dict[str, Any], tokens: tuple[str, ...]) -> str:
    """Explain why one legacy branch is outside the shared clean-room grammar."""

    if is_truncated_inflection_source(record):
        return "truncated_without_recoverable_prefix"
    return "remaining_syntax"


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    path_counts: Counter[str] = Counter()
    fallback_reason_counts: Counter[str] = Counter()
    fallback_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    fallback_reason_groups: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    noun_records = 0
    branch_count = 0
    records_with_fallback: set[tuple[str, str, str]] = set()
    truncated_records: set[tuple[str, str, str]] = set()

    for record in records:
        if str(record.get("upos") or "").upper() != "NOUN":
            continue
        noun_records += 1
        pattern = inflection_text(record)
        if pattern is None:
            path_counts["no_inflection_text"] += 1
            continue
        branches = split_alternative_branches(_clean_notation_structure(pattern))
        if not branches:
            path_counts["untokenized"] += 1
            continue

        lemma = str(record.get("normaliserat_ord") or "")
        homonym = str(record.get("homonr") or "")
        record_id = str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or "")
        if is_truncated_inflection_source(record):
            truncated_records.add((record_id, homonym, lemma))
        for branch_index, branch in enumerate(branches):
            branch_count += 1
            path = branch_path(record, branch.tokens)
            path_counts[path] += 1
            if path != "legacy_fallback":
                continue
            records_with_fallback.add((record_id, homonym, lemma))
            reason = fallback_reason(record, branch.tokens)
            fallback_reason_counts[reason] += 1
            example = {
                "lemma": lemma,
                "homonym_number": homonym,
                "record_id": record_id,
                "branch": str(branch_index + 1),
                "tokens": " ".join(branch.tokens),
                "ordkl": str(record.get("ordkl") or ""),
            }
            fallback_groups[pattern].append(example)
            fallback_reason_groups[reason][pattern].append(example)

    groups = sorted(fallback_groups.items(), key=lambda item: (-len(item[1]), item[0]))
    reason_groups = {
        reason: [
            {
                "notation": notation,
                "count": len(members),
                "examples": members[:20],
            }
            for notation, members in sorted(
                grouped.items(), key=lambda item: (-len(item[1]), item[0])
            )
        ]
        for reason, grouped in fallback_reason_groups.items()
    }
    return {
        "noun_records": noun_records,
        "branches": branch_count,
        "path_counts": dict(path_counts.most_common()),
        "truncated_records": len(truncated_records),
        "shared_truncated_partial_branches": path_counts.get("shared_truncated_partial", 0),
        "records_with_legacy_fallback": len(records_with_fallback),
        "legacy_fallback_branches": path_counts.get("legacy_fallback", 0),
        "legacy_fallback_notations": len(fallback_groups),
        "fallback_reason_counts": dict(fallback_reason_counts.most_common()),
        "fallback_groups": [
            {
                "notation": notation,
                "count": len(members),
                "examples": members[:20],
            }
            for notation, members in groups
        ],
        "fallback_reason_groups": reason_groups,
    }


def _render_groups(lines: list[str], groups: list[dict[str, Any]]) -> None:
    for index, group in enumerate(groups[:100], start=1):
        lines.append("")
        lines.append(f"{index}. {group['count']} | {group['notation']}")
        for example in group["examples"][:8]:
            homonym = f" ({example['homonym_number']})" if example["homonym_number"] else ""
            lines.append(
                f"   {example['lemma']}{homonym} | branch {example['branch']} | "
                f"tokens={example['tokens']!r} | ordkl={example['ordkl']!r}"
            )


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: täckning av gemensam slotmotor",
        "",
        "Varje böjningsbranch klassificeras oberoende. Trunkerade källrader",
        "tolkas med samma shared-grammatik så långt ett komplett prefix räcker;",
        "ingen saknad slutform eller slot gissas fram.",
        "",
        f"NOUN-poster: {summary['noun_records']}",
        f"Böjningsbrancher: {summary['branches']}",
        f"Trunkerade poster: {summary['truncated_records']}",
        f"Shared trunkerade partial-brancher: {summary['shared_truncated_partial_branches']}",
        f"Poster med legacy-fallback: {summary['records_with_legacy_fallback']}",
        f"Legacy-fallback-brancher: {summary['legacy_fallback_branches']}",
        f"Legacy-fallback-notationer: {summary['legacy_fallback_notations']}",
        "",
        "Vägar:",
    ]
    for path, count in summary["path_counts"].items():
        lines.append(f"  {count:7d}  {path}")

    lines.extend(["", "Legacy-fallback efter orsak:"])
    if not summary["fallback_reason_counts"]:
        lines.append("        0  (inga)")
    for reason, count in summary["fallback_reason_counts"].items():
        lines.append(f"  {count:7d}  {reason}")

    for reason in ("remaining_syntax", "truncated_without_recoverable_prefix"):
        groups = summary["fallback_reason_groups"].get(reason, [])
        lines.extend(["", f"{reason} – största notationer:"])
        _render_groups(lines, groups)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    records = prepare_noun_variant_records(read_jsonl(args.saol))
    summary = analyze(records)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"NOUN-poster: {summary['noun_records']}")
    print(f"Böjningsbrancher: {summary['branches']}")
    print(f"Trunkerade poster: {summary['truncated_records']}")
    print(f"Shared trunkerade partial-brancher: {summary['shared_truncated_partial_branches']}")
    print(f"Poster med legacy-fallback: {summary['records_with_legacy_fallback']}")
    print(f"Legacy-fallback-brancher: {summary['legacy_fallback_branches']}")
    print(f"Legacy-fallback-notationer: {summary['legacy_fallback_notations']}")
    for path, count in summary["path_counts"].items():
        print(f"{path}: {count}")
    for reason, count in summary["fallback_reason_counts"].items():
        print(f"{reason}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
