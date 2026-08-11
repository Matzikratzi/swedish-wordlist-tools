from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .saol_notation import split_alternative_branches
from .saol_source_policy import inflection_text, is_truncated_inflection_source

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-notation-inventory.txt")
DEFAULT_JSON = Path("reports/saol14-verb-notation-inventory.json")

_PUNCTUATION = {",", ";", "_", "H", "el."}
_LABEL_RE = re.compile(r"^[^+\-][^\s]*\.$")
_RELATIVE_RE = re.compile(r"^[+-].+")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or "")


def _looks_like_atom(token: str) -> bool:
    if token in _PUNCTUATION:
        return False
    if token.endswith(":"):
        return False
    if _LABEL_RE.match(token):
        return False
    return True


def _branch_shape(tokens: tuple[str, ...]) -> str:
    parts: list[str] = []
    for token in tokens:
        if token in {",", ";"}:
            parts.append(token)
        elif token in {"_", "H", "el."}:
            parts.append(token)
        elif token.endswith(":"):
            parts.append("COMMENT_LABEL")
        elif _LABEL_RE.match(token):
            parts.append("SLOT_LABEL")
        elif _RELATIVE_RE.match(token):
            parts.append("RELATIVE_ATOM")
        else:
            parts.append("EXPLICIT_ATOM")
    return " ".join(parts)


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    verb_records = 0
    without_text = 0
    truncated_records = 0
    branch_count = 0
    notation_counts: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    atom_length_counts: Counter[int] = Counter()
    example_by_shape: dict[str, list[dict[str, str]]] = defaultdict(list)

    for record in records:
        if str(record.get("upos") or "").upper() != "VERB":
            continue
        verb_records += 1
        if is_truncated_inflection_source(record):
            truncated_records += 1
        pattern = inflection_text(record)
        if pattern is None:
            without_text += 1
            continue
        notation_counts[pattern] += 1
        branches = split_alternative_branches(pattern)
        for branch_index, branch in enumerate(branches, start=1):
            branch_count += 1
            tokens = branch.tokens
            shape = _branch_shape(tokens)
            shape_counts[shape] += 1
            atom_length_counts[sum(1 for token in tokens if _looks_like_atom(token))] += 1
            for token in tokens:
                token_counts[token] += 1
                if _LABEL_RE.match(token) or token.endswith(":"):
                    label_counts[token] += 1
            if len(example_by_shape[shape]) < 5:
                example_by_shape[shape].append(
                    {
                        "lemma": str(record.get("normaliserat_ord") or ""),
                        "homonym_number": str(record.get("homonr") or ""),
                        "record_id": _record_id(record),
                        "branch": str(branch_index),
                        "text": pattern,
                        "tokens": " ".join(tokens),
                        "ordkl": str(record.get("ordkl") or ""),
                    }
                )

    top_shapes = [
        {"shape": shape, "count": count, "examples": example_by_shape[shape]}
        for shape, count in shape_counts.most_common(100)
    ]
    return {
        "verb_records": verb_records,
        "without_inflection_text": without_text,
        "truncated_records": truncated_records,
        "branches": branch_count,
        "distinct_notations": len(notation_counts),
        "distinct_branch_shapes": len(shape_counts),
        "atom_length_counts": dict(sorted(atom_length_counts.items())),
        "top_labels": label_counts.most_common(100),
        "top_tokens": token_counts.most_common(100),
        "top_notations": notation_counts.most_common(100),
        "top_shapes": top_shapes,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 VERB: inventering av notation före clean-room-refaktorering",
        "",
        "Inventeringen tolkar inga verbformer. Den beskriver endast den notation",
        "som faktiskt finns i JSONL och använder befintlig SAOL-branch-tokenisering.",
        "",
        f"VERB-poster: {summary['verb_records']}",
        f"Utan böjningstext: {summary['without_inflection_text']}",
        f"Trunkerade poster: {summary['truncated_records']}",
        f"Böjningsbrancher: {summary['branches']}",
        f"Unika notationer: {summary['distinct_notations']}",
        f"Unika branchformer: {summary['distinct_branch_shapes']}",
        "",
        "Antal formatomer per branch:",
    ]
    for count, occurrences in summary["atom_length_counts"].items():
        lines.append(f"  {int(count):2d}: {occurrences}")

    lines.extend(["", "Vanligaste etiketter/kommentarmarkörer:"])
    for token, count in summary["top_labels"][:50]:
        lines.append(f"  {count:7d}  {token}")

    lines.extend(["", "Vanligaste branchformer:"])
    for index, group in enumerate(summary["top_shapes"][:40], start=1):
        lines.append("")
        lines.append(f"{index}. {group['count']} | {group['shape']}")
        for example in group["examples"][:3]:
            homonym = f" ({example['homonym_number']})" if example["homonym_number"] else ""
            lines.append(
                f"   {example['lemma']}{homonym} | branch {example['branch']} | "
                f"text={example['text']!r} | tokens={example['tokens']!r}"
            )

    lines.extend(["", "Vanligaste kompletta notationer:"])
    for index, pair in enumerate(summary["top_notations"][:40], start=1):
        notation, count = pair
        lines.append(f"  {index:2d}. {count:7d} | {notation}")
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
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"VERB-poster: {summary['verb_records']}")
    print(f"Utan böjningstext: {summary['without_inflection_text']}")
    print(f"Trunkerade poster: {summary['truncated_records']}")
    print(f"Böjningsbrancher: {summary['branches']}")
    print(f"Unika notationer: {summary['distinct_notations']}")
    print(f"Unika branchformer: {summary['distinct_branch_shapes']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
