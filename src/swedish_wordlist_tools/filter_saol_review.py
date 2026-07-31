from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("reports/saol14-unmatched-saol-bars.jsonl")
DEFAULT_OUTPUT = Path("reports/saol14-manual-review.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-manual-review-summary.json")

MATCHED_REASONS = {
    "unique_saol_bar_split",
    "multiple_saol_bar_splits",
}


def remaining_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only SAOL rows that were not matched by an explicit bar split."""
    return [
        dict(row)
        for row in rows
        if str(row.get("saol_bar_reason", "")) not in MATCHED_REASONS
    ]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def filter_saol_review(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    source_rows = list(read_jsonl(input_path))
    rows = remaining_rows(source_rows)
    rows.sort(key=lambda row: str(row.get("lemma", "")).casefold())
    _write_jsonl(output_path, rows)

    counts = Counter(str(row.get("saol_bar_reason", "")) for row in rows)
    summary: dict[str, Any] = {
        "input": str(input_path),
        "output": str(output_path),
        "input_records": len(source_rows),
        "removed_matched_records": len(source_rows) - len(rows),
        "remaining_records": len(rows),
        "remaining_counts": dict(sorted(counts.items())),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove SAOL entries matched by explicit lodstreck and write the manual-review remainder"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = filter_saol_review(args.input, args.output, args.summary)
    print(f"Indata: {summary['input_records']}")
    print(f"Borttagna matchade poster: {summary['removed_matched_records']}")
    print(f"Kvar för manuell granskning: {summary['remaining_records']}")
    for reason, count in summary["remaining_counts"].items():
        print(f"{reason}: {count}")
    print(f"Återstod: {summary['output']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
