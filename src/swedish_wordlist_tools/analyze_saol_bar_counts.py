from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-bar-counts.txt")
DEFAULT_JSON = Path("reports/saol14-bar-counts.json")


def build_report(path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    counts: Counter[int] = Counter()
    examples: dict[int, list[dict[str, str]]] = defaultdict(list)
    total = 0
    for record in read_jsonl(path):
        total += 1
        stycke = str(record.get("stycke") or "")
        number = stycke.count("|")
        counts[number] += 1
        if number >= 2 and len(examples[number]) < 100:
            examples[number].append({
                "lemma": str(record.get("normaliserat_ord") or ""),
                "homonr": str(record.get("homonr") or ""),
                "upos": str(record.get("upos") or ""),
                "stycke": stycke,
                "text": str(record.get("text") or ""),
            })
    return {
        "records": total,
        "bar_counts": {str(k): v for k, v in sorted(counts.items())},
        "records_with_multiple_bars": sum(v for k, v in counts.items() if k >= 2),
        "examples": {str(k): v for k, v in sorted(examples.items())},
        "note": "Replacement operations use the final vertical bar and preserve everything before it.",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [f"Poster: {report['records']}", "", "Antal lodstreck i stycke:"]
    for number, count in report["bar_counts"].items():
        lines.append(f"  {number:>3}: {count}")
    lines.append(f"\nPoster med minst två lodstreck: {report['records_with_multiple_bars']}")
    for number, rows in report.get("examples", {}).items():
        lines.extend(["", f"Exempel med {number} lodstreck:"])
        for row in rows[:30]:
            lines.append(f"  {row['lemma']}#{row['homonr']} [{row['upos']}] | {row['stycke']} | {row['text']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Count vertical bars in SAOL14 stycke fields")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(render_text(report).split("\n\n", 1)[0])
    print(f"Poster med minst två lodstreck: {report['records_with_multiple_bars']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
