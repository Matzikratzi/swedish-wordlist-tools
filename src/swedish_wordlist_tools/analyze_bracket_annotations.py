from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-bracket-annotations.txt")
DEFAULT_JSON = Path("reports/saol14-bracket-annotations-summary.json")

_BRACKET_RE = re.compile(r"\[[^\[\]]+\]")


def analyse_bracket_annotations(
    records: Iterable[dict[str, Any]],
    examples_per_group: int = 10,
) -> dict[str, Any]:
    annotation_counts: Counter[str] = Counter()
    notation_counts: Counter[str] = Counter()
    annotation_examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    notation_examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    records_with_brackets = 0

    for record in records:
        notation = str(record.get("text", "")).strip()
        if not notation or notation == "(null)":
            continue
        annotations = _BRACKET_RE.findall(notation)
        if not annotations:
            continue

        records_with_brackets += 1
        lemma = str(record.get("normaliserat_ord", "")).strip()
        homonym = str(record.get("homonr", "")).strip()
        example = {"lemma": lemma, "homonym_number": homonym, "notation": notation}

        notation_counts[notation] += 1
        if len(notation_examples[notation]) < examples_per_group:
            notation_examples[notation].append(example)

        for annotation in dict.fromkeys(annotations):
            annotation_counts[annotation] += 1
            if len(annotation_examples[annotation]) < examples_per_group:
                annotation_examples[annotation].append(example)

    annotations = [
        {
            "annotation": annotation,
            "count": count,
            "examples": annotation_examples[annotation],
        }
        for annotation, count in annotation_counts.most_common()
    ]
    notations = [
        {
            "notation": notation,
            "count": count,
            "annotations": _BRACKET_RE.findall(notation),
            "examples": notation_examples[notation],
        }
        for notation, count in notation_counts.most_common()
    ]
    return {
        "records_with_brackets": records_with_brackets,
        "unique_annotations": len(annotations),
        "unique_notations": len(notations),
        "annotations": annotations,
        "notations": notations,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Poster med hakparenteser: {summary['records_with_brackets']}",
        f"Unika hakparentesmarkeringar: {summary['unique_annotations']}",
        f"Unika fullständiga notationer: {summary['unique_notations']}",
        "",
        "Per hakparentesmarkering:",
    ]
    for index, group in enumerate(summary["annotations"], 1):
        examples = ", ".join(
            f"{item['lemma']} ({item['homonym_number']})"
            for item in group["examples"]
        )
        lines.extend(
            [
                f"{index}. {group['annotation']} — {group['count']} poster",
                f"   Exempel: {examples or '–'}",
                "",
            ]
        )

    lines.append("Per fullständig notation:")
    for index, group in enumerate(summary["notations"], 1):
        examples = ", ".join(
            f"{item['lemma']} ({item['homonym_number']})"
            for item in group["examples"]
        )
        lines.extend(
            [
                f"{index}. {group['notation']} — {group['count']} poster",
                f"   Exempel: {examples or '–'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def analyse_file(
    input_path: Path = DEFAULT_INPUT,
    text_path: Path = DEFAULT_TEXT,
    json_path: Path = DEFAULT_JSON,
    examples_per_group: int = 10,
) -> dict[str, Any]:
    summary = analyse_bracket_annotations(read_jsonl(input_path), examples_per_group)
    summary["input"] = str(input_path)
    summary["text"] = str(text_path)
    summary["json"] = str(json_path)

    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List bracket annotations in SAOL14 inflection fields"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--examples", type=int, default=10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_file(args.input, args.text, args.json, args.examples)
    print(f"Poster med hakparenteser: {summary['records_with_brackets']}")
    print(f"Unika hakparentesmarkeringar: {summary['unique_annotations']}")
    print(f"Unika fullständiga notationer: {summary['unique_notations']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
