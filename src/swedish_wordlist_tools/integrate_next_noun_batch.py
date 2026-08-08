from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .classify_form_mismatches import (
    DEFAULT_JSONL,
    DEFAULT_SUMMARY,
    DEFAULT_TEXT,
    UNCLASSIFIED,
    build_summary,
    render_text,
    write_jsonl,
)
from .classify_next_noun_batch import classify_batch_row


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def integrate_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    changed = 0
    for row in rows:
        if str(row.get("mismatch_classification", "")) != UNCLASSIFIED:
            result.append(dict(row))
            continue

        classification, rationale = classify_batch_row(row)
        if classification == UNCLASSIFIED:
            result.append(dict(row))
            continue

        updated = dict(row)
        updated["mismatch_classification"] = classification
        updated["classification_rationale"] = rationale
        result.append(updated)
        changed += 1
    return result, changed


def integrate_file(
    input_path: Path = DEFAULT_JSONL,
    *,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    rows, changed = integrate_rows(read_jsonl(input_path))
    write_jsonl(jsonl_path, rows)
    summary = build_summary(rows)
    summary.update(
        {
            "batch_integrated_records": changed,
            "input": str(input_path),
            "jsonl": str(jsonl_path),
            "summary": str(summary_path),
            "text": str(text_path),
        }
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Integrera verifierade NOUN-batchklassningar i huvudrapporten")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    summary = integrate_file(
        args.input,
        jsonl_path=args.jsonl,
        summary_path=args.summary,
        text_path=args.text,
    )
    print(f"Batchintegrerade: {summary['batch_integrated_records']}")
    print(f"Klassificerade totalt: {summary['classified_records']}")
    print(f"Oklassificerade: {summary['unclassified_records']}")
    for name, count in summary["classification_counts"].items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
