from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .jsonl import read_jsonl
from .saol_source_policy import is_truncated_inflection_source

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-x-ordkl-inventory.txt")
DEFAULT_JSON = Path("reports/saol14-x-ordkl-inventory.json")


def ordkl_head(record) -> str:
    raw = str(record.get("ordkl") or "").strip()
    if not raw:
        return "(saknas)"
    return raw.split("<i", 1)[0].strip() or "(saknas)"


def primary_text(record) -> str:
    value = record.get("text")
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def analyze(records):
    total = 0
    with_text = 0
    truncated = 0
    counts = Counter()
    text_counts = Counter()
    examples = defaultdict(list)
    for record in records:
        if str(record.get("upos") or "").upper() != "X":
            continue
        total += 1
        head = ordkl_head(record)
        counts[head] += 1
        text = primary_text(record)
        if text:
            with_text += 1
            text_counts[head] += 1
            truncated += int(is_truncated_inflection_source(record))
            if len(examples[head]) < 5:
                examples[head].append({
                    "lemma": str(record.get("normaliserat_ord") or ""),
                    "homonr": str(record.get("homonr") or ""),
                    "text": text,
                    "ordkl": str(record.get("ordkl") or ""),
                })
    groups = []
    for head, count in counts.most_common():
        groups.append({
            "ordkl": head,
            "records": count,
            "text_records": text_counts[head],
            "no_text_records": count - text_counts[head],
            "examples": examples[head],
        })
    return {
        "x_records": total,
        "text_records": with_text,
        "no_text_records": total - with_text,
        "truncated_records": truncated,
        "distinct_ordkl_heads": len(counts),
        "groups": groups,
    }


def render_text(report):
    lines = [
        "SAOL14 X: ordkl-inventering",
        "",
        "UPOS X behandlas här inte som en grammatisk ordklass. Poster grupperas",
        "efter SAOL:s ordkl-fält före eventuell kursiverad böjningsnotation.",
        "",
        f"X-poster: {report['x_records']}",
        f"Med textfält: {report['text_records']}",
        f"Utan textfält: {report['no_text_records']}",
        f"Trunkerade textposter: {report['truncated_records']}",
        f"Distinkta ordkl-huvuden: {report['distinct_ordkl_heads']}",
        "",
        "ordkl                                      poster    text  utan text",
    ]
    for group in report["groups"]:
        lines.append(
            f"{group['ordkl'][:40]:40} {group['records']:7d} {group['text_records']:7d} {group['no_text_records']:10d}"
        )
    lines.extend(["", "Exempel bland grupper med textfält:"])
    for group in report["groups"]:
        if not group["text_records"]:
            continue
        lines.append(f"\n[{group['ordkl']}] poster={group['records']} text={group['text_records']}")
        for row in group["examples"]:
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) | text='{row['text']}' | ordkl='{row['ordkl']}'"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL14 UPOS X by ordkl")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"X-poster: {report['x_records']}")
    print(f"Med textfält: {report['text_records']}")
    print(f"Distinkta ordkl-huvuden: {report['distinct_ordkl_heads']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
