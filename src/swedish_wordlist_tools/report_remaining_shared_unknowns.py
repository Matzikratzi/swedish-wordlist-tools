from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build_shared_wordlist import build_rows
from .jsonl import read_jsonl

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-final-unknowns.txt")
DEFAULT_JSON = Path("reports/saol14-final-unknowns.json")


def analyze(records):
    rows, summary = build_rows(records)
    unknown = [row for row in rows if row.get("classification") == "UNKNOWN_WORD"]
    return {"summary": summary, "unknown": unknown}


def render(report):
    lines = [
        "SAOL14: kvarvarande UNKNOWN efter full shared/X-routing",
        "",
        f"UNKNOWN: {len(report['unknown'])}",
        "",
    ]
    for row in report["unknown"]:
        lines.append(
            f"  {row['form']} | upos={','.join(row.get('upos') or []) or '-'} | "
            f"source={','.join(row.get('source_record_ids') or []) or '-'} | "
            f"provenance={','.join(row.get('provenance') or []) or '-'}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Report remaining UNKNOWN forms after current shared generation")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"UNKNOWN: {len(report['unknown'])}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
