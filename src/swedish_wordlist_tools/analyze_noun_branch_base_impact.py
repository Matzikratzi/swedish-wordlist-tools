from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry
from .saol_notation import split_alternative_branches

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_CURRENT = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-branch-base-impact.txt")
DEFAULT_JSON = Path("reports/saol14-noun-branch-base-impact.json")

TARGET_NOTATION = "+det; pl. +, best. pl. +dena _ +t +n"

_SUP_ELEMENT_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _clean_form(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return re.sub(r"\s+", " ", text).strip()


def _written_forms(entry: Any) -> set[str]:
    if entry is None:
        return set()
    return {form.written_form for form in entry.word_forms if form.written_form}


def _current_by_record(rows: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        record_id = str(row.get("record_id") or "")
        for form in row.get("forms", []):
            written = str(form.get("written_form") or "")
            if written:
                result[record_id].add(written)
    return result


def _ordered_branch_bases(rows: list[dict[str, Any]], branch_count: int) -> tuple[str, ...] | None:
    if branch_count != 2:
        return None
    lemma = _clean_form(rows[0].get("normaliserat_ord"))
    if not lemma:
        return None
    variants: list[str] = []
    for row in rows:
        variant = _clean_form(row.get("ord"))
        if variant and variant.casefold() not in {item.casefold() for item in variants}:
            variants.append(variant)
    primary = next((value for value in variants if value.casefold() == lemma.casefold()), lemma)
    others = [value for value in variants if value.casefold() != primary.casefold()]
    if len(others) != 1:
        return None
    return primary, others[0]


def _simulate_group(rows: list[dict[str, Any]]) -> set[str] | None:
    record = rows[0]
    notation = str(record.get("text") or "")
    if notation != TARGET_NOTATION:
        return None
    branches = split_alternative_branches(notation)
    bases = _ordered_branch_bases(rows, len(branches))
    if len(branches) != 2 or bases is None:
        return None

    result: set[str] = set()
    for branch, base in zip(branches, bases):
        branch_record = dict(record)
        branch_record["normaliserat_ord"] = base
        branch_record["text"] = branch.text
        # The original stycke describes the main headword.  For the alternative
        # base this target pattern uses only append/unchanged operations, so no
        # compound-tail replacement evidence is needed.
        entry = complete_noun_entry(branch_record, None)
        if entry is None:
            return None
        result.update(_written_forms(entry))
    return result


def analyze(records: Iterable[dict[str, Any]], current_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if _saol_upos(record) == "NOUN":
            groups[_record_id(record)].append(record)

    current = _current_by_record(current_rows)
    changes: list[dict[str, Any]] = []
    for record_id, rows in groups.items():
        simulated = _simulate_group(rows)
        if simulated is None:
            continue
        before = current.get(record_id, set())
        changes.append(
            {
                "record_id": record_id,
                "lemma": str(rows[0].get("normaliserat_ord") or ""),
                "ord_variants": list(_ordered_branch_bases(rows, 2) or ()),
                "before": sorted(before, key=str.casefold),
                "after": sorted(simulated, key=str.casefold),
                "added": sorted(simulated - before, key=str.casefold),
                "removed": sorted(before - simulated, key=str.casefold),
            }
        )

    changes.sort(key=lambda row: (str(row["lemma"]).casefold(), str(row["record_id"])))
    return {
        "target_notation": TARGET_NOTATION,
        "candidate_groups": len(changes),
        "groups_with_changes": sum(bool(row["added"] or row["removed"]) for row in changes),
        "unique_added_forms": len({form.casefold() for row in changes for form in row["added"]}),
        "unique_removed_forms": len({form.casefold() for row in changes for form in row["removed"]}),
        "changes": changes,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        f"Notation: {summary['target_notation']}",
        f"Kandidatgrupper: {summary['candidate_groups']}",
        f"Grupper vars former ändras: {summary['groups_with_changes']}",
        f"Unika former som tillkommer: {summary['unique_added_forms']}",
        f"Unika former som försvinner: {summary['unique_removed_forms']}",
        "",
        "Påverkan per grupp:",
    ]
    for row in summary["changes"]:
        lines.append(f"  {row['lemma']} | record_id={row['record_id']}")
        lines.append(f"    baser: {', '.join(row['ord_variants'])}")
        lines.append(f"    tillkommer: {', '.join(row['added']) or '-'}")
        lines.append(f"    försvinner: {', '.join(row['removed']) or '-'}")
    if not summary["changes"]:
        lines.append("  (inga)")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate using sibling ord variants as bases for a proven two-branch noun notation"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze(read_jsonl(args.saol), read_jsonl(args.current))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Kandidatgrupper: {summary['candidate_groups']}")
    print(f"Grupper vars former ändras: {summary['groups_with_changes']}")
    print(f"Unika former som tillkommer: {summary['unique_added_forms']}")
    print(f"Unika former som försvinner: {summary['unique_removed_forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
