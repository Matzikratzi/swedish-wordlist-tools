from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_notation import parse_form_operation

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSON = Path("reports/saol14-semicolon-boundaries.json")
DEFAULT_TEXT = Path("reports/saol14-semicolon-boundaries.txt")

_HTML_TAG = re.compile(r"</?[^>]+>")
_BRACKET_COMMENT = re.compile(r"\s*\[[^\]]*\]")


def _clean(text: str) -> str:
    text = _HTML_TAG.sub("", text)
    text = _BRACKET_COMMENT.sub("", text)
    return " ".join(text.split())


def token_before_semicolon(clause: str) -> str | None:
    cleaned = _clean(clause).strip()
    if not cleaned:
        return None
    return cleaned.split()[-1]


def semicolon_predecessors(text: str) -> tuple[str, ...]:
    parts = _clean(text).split(";")
    if len(parts) < 2:
        return ()
    result: list[str] = []
    for clause in parts[:-1]:
        token = token_before_semicolon(clause)
        if token:
            result.append(token)
    return tuple(result)


def classify_predecessor(token: str) -> str:
    stripped = token.strip("()")
    operation = parse_form_operation(stripped)
    if operation is not None:
        return operation.kind.value
    if stripped.endswith(":"):
        return "comment_marker"
    if stripped.endswith("."):
        return "label"
    return "unclassified"


def analyze_semicolon_boundaries(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    records_with_semicolon = 0
    boundary_count = 0

    for record in records:
        text = str(record.get("text") or "")
        predecessors = semicolon_predecessors(text)
        if not predecessors:
            continue
        records_with_semicolon += 1
        lemma = str(record.get("normaliserat_ord") or record.get("ord") or "")
        for token in predecessors:
            boundary_count += 1
            classification = classify_predecessor(token)
            counts[classification] += 1
            token_counts[token.casefold()] += 1
            if len(examples[classification]) < 20:
                examples[classification].append(
                    {
                        "lemma": lemma,
                        "token": token,
                        "text": text,
                        "stycke": str(record.get("stycke") or ""),
                        "subnr": record.get("subnr"),
                    }
                )

    groups = [
        {
            "classification": classification,
            "count": count,
            "examples": examples[classification],
        }
        for classification, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    most_common_tokens = [
        {"token": token, "count": count}
        for token, count in token_counts.most_common(100)
    ]
    return {
        "records_with_semicolon": records_with_semicolon,
        "semicolon_boundaries": boundary_count,
        "classification_counts": dict(sorted(counts.items())),
        "groups": groups,
        "most_common_predecessors": most_common_tokens,
    }


def render_report(analysis: dict[str, Any]) -> str:
    lines = [
        f"Poster med semikolon: {analysis['records_with_semicolon']}",
        f"Semikolongränser: {analysis['semicolon_boundaries']}",
        "Klassningar: "
        + ", ".join(
            f"{key}={value}"
            for key, value in analysis["classification_counts"].items()
        ),
        "",
    ]
    for group in analysis["groups"]:
        lines.append(
            f"=== {group['classification']} ({group['count']}) ==="
        )
        for example in group["examples"]:
            lines.append(
                f"  {example['lemma']} | före ;: {example['token']} | "
                f"{example['text']} | stycke={example['stycke']} | "
                f"subnr={example['subnr']}"
            )
        lines.append("")
    lines.append("Vanligaste token före semikolon:")
    for item in analysis["most_common_predecessors"]:
        lines.append(f"  {item['count']:5}  {item['token']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory tokens immediately before semicolons in SAOL text"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = analyze_semicolon_boundaries(read_jsonl(args.saol))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.text.write_text(render_report(analysis), encoding="utf-8")
    print(f"Poster med semikolon: {analysis['records_with_semicolon']}")
    print(f"Semikolongränser: {analysis['semicolon_boundaries']}")
    print(f"Klassningar: {analysis['classification_counts']}")
    print(f"Rapport: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
