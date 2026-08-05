from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSON = Path("reports/saol14-colon-markers.json")
DEFAULT_TEXT = Path("reports/saol14-colon-markers.txt")

_HTML_TAG = re.compile(r"<[^>]+>")
_TOKEN = re.compile(r"[^\s;,()\[\]]+")


def _clean_text(value: str) -> str:
    return _HTML_TAG.sub("", value)


def colon_tokens(value: str) -> tuple[str, ...]:
    """Return lexical tokens whose final visible character is a colon.

    Colons inside forms such as ``BB:t`` and operation payloads such as ``+:n``
    are intentionally excluded because the colon is not token-final there.
    """

    return tuple(
        token
        for token in _TOKEN.findall(_clean_text(value))
        if token.endswith(":") and token not in {"+:", "-:"}
    )


def analyze_colon_markers(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "lemmas": set(), "examples": []}
    )
    record_count = 0
    occurrence_count = 0

    for record in records:
        text = str(record.get("text", ""))
        tokens = colon_tokens(text)
        if not tokens:
            continue
        record_count += 1
        lemma = str(record.get("normaliserat_ord", ""))
        for token in tokens:
            occurrence_count += 1
            key = token.casefold()
            item = grouped[key]
            item["count"] += 1
            if lemma:
                item["lemmas"].add(lemma)
            if len(item["examples"]) < 8:
                item["examples"].append(
                    {
                        "lemma": lemma,
                        "token": token,
                        "text": text,
                        "stycke": str(record.get("stycke", "")),
                        "subnr": record.get("subnr"),
                    }
                )

    groups = []
    for key, item in grouped.items():
        groups.append(
            {
                "token": key,
                "count": item["count"],
                "lemma_count": len(item["lemmas"]),
                "lemmas": sorted(item["lemmas"], key=str.casefold),
                "examples": item["examples"],
            }
        )
    groups.sort(key=lambda item: (-item["count"], item["token"]))

    return {
        "records_with_colon_markers": record_count,
        "colon_marker_occurrences": occurrence_count,
        "unique_colon_markers": len(groups),
        "groups": groups,
    }


def render_report(analysis: dict[str, Any]) -> str:
    lines = [
        f"Poster med kolonmarkörer: {analysis['records_with_colon_markers']}",
        f"Förekomster: {analysis['colon_marker_occurrences']}",
        f"Unika kolonmarkörer: {analysis['unique_colon_markers']}",
        "",
        "Kolonmarkörer sorterade efter frekvens:",
    ]
    for index, group in enumerate(analysis["groups"], 1):
        lines.extend(
            [
                "",
                f"=== {index}. {group['token']} ({group['count']} förekomster, "
                f"{group['lemma_count']} lemman) ===",
            ]
        )
        for example in group["examples"]:
            lines.append(
                f"  {example['lemma']} | {example['text']} | "
                f"stycke={example['stycke']} | subnr={example['subnr']}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory all token-final colon markers in SAOL text fields"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = analyze_colon_markers(read_jsonl(args.saol))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.text.write_text(render_report(analysis), encoding="utf-8")
    print(f"Poster med kolonmarkörer: {analysis['records_with_colon_markers']}")
    print(f"Förekomster: {analysis['colon_marker_occurrences']}")
    print(f"Unika kolonmarkörer: {analysis['unique_colon_markers']}")
    print(f"Rapport: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
