from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_notation import tokenize_notation

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSON = Path("reports/saol14-nonoverlap-replacements.json")
DEFAULT_TEXT = Path("reports/saol14-nonoverlap-replacements.txt")

_HTML_TAG = re.compile(r"</?[^>]+>")
_DIVIDERS = str.maketrans("", "", "·.")
_HYPHENS = "‐‑–—"


def clean_stycke(stycke: str) -> str:
    text = _HTML_TAG.sub("", stycke)
    for hyphen in _HYPHENS:
        text = text.replace(hyphen, "-")
    return text.translate(_DIVIDERS)


def split_compound(stycke: str) -> tuple[str, str] | None:
    cleaned = clean_stycke(stycke)
    if "|" not in cleaned:
        return None
    prefix, head = cleaned.rsplit("|", 1)
    if not prefix or not head:
        return None
    return prefix, head


def common_prefix_length(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left.casefold(), right.casefold()):
        if a != b:
            break
        count += 1
    return count


def replacement_tokens(text: str) -> tuple[str, ...]:
    tokens = tokenize_notation(text)
    if not tokens:
        return ()
    return tuple(token for token in tokens if token.startswith("-") and len(token) > 1)


def analyze_nonoverlap_replacements(
    records: Iterable[dict[str, Any]], *, overlap_threshold: int = 2
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    overlap_counts: Counter[int] = Counter()
    records_seen = 0

    for record in records:
        compound = split_compound(str(record.get("stycke") or ""))
        if compound is None:
            continue
        tokens = replacement_tokens(str(record.get("text") or ""))
        if not tokens:
            continue
        records_seen += 1
        prefix, head = compound
        lemma = str(record.get("normaliserat_ord") or record.get("ord") or "")
        for token in tokens:
            payload = token[1:]
            overlap = common_prefix_length(head, payload)
            overlap_counts[overlap] += 1
            if overlap >= overlap_threshold:
                continue
            rows.append(
                {
                    "lemma": lemma,
                    "stycke": str(record.get("stycke") or ""),
                    "text": str(record.get("text") or ""),
                    "prefix": prefix,
                    "head": head,
                    "token": token,
                    "payload": payload,
                    "prefix_overlap": overlap,
                    "without_hyphen": prefix + payload,
                    "with_hyphen": prefix.rstrip("-") + "-" + payload,
                    "subnr": record.get("subnr"),
                    "source": str(record.get("source") or ""),
                }
            )

    rows.sort(key=lambda row: (row["lemma"].casefold(), row["token"].casefold()))
    return {
        "compound_records_with_replacements": records_seen,
        "nonoverlap_replacement_count": len(rows),
        "overlap_threshold": overlap_threshold,
        "overlap_counts": {str(key): value for key, value in sorted(overlap_counts.items())},
        "rows": rows,
    }


def render_report(analysis: dict[str, Any]) -> str:
    lines = [
        f"Sammansatta poster med ersättningar: {analysis['compound_records_with_replacements']}",
        f"Ersättningar med överlapp < {analysis['overlap_threshold']}: {analysis['nonoverlap_replacement_count']}",
        f"Överlappsfördelning: {analysis['overlap_counts']}",
        "",
    ]
    for index, row in enumerate(analysis["rows"], start=1):
        lines.extend(
            [
                f"=== {index}. {row['lemma']} | {row['token']} ===",
                f"stycke: {row['stycke']}",
                f"text: {row['text']}",
                f"prefix: {row['prefix']}",
                f"ersatt led: {row['head']}",
                f"payload: {row['payload']}",
                f"gemensamt prefix: {row['prefix_overlap']}",
                f"utan bindestreck: {row['without_hyphen']}",
                f"med bindestreck: {row['with_hyphen']}",
                f"subnr: {row['subnr']}",
                f"source: {row['source']}",
                "",
            ]
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory bar-marked replacement operations whose payload does not overlap the replaced compound head"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--overlap-threshold", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = analyze_nonoverlap_replacements(
        read_jsonl(args.saol), overlap_threshold=args.overlap_threshold
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.text.write_text(render_report(analysis), encoding="utf-8")
    print(
        "Sammansatta poster med ersättningar:",
        analysis["compound_records_with_replacements"],
    )
    print(
        f"Ersättningar med överlapp < {analysis['overlap_threshold']}:",
        analysis["nonoverlap_replacement_count"],
    )
    print(f"Rapport: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
