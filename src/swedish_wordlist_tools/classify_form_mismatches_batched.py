from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .classify_form_mismatches import (
    DEFAULT_INPUT,
    DEFAULT_JSONL,
    DEFAULT_SUMMARY,
    DEFAULT_TEXT,
    UNCLASSIFIED,
    build_summary,
    classify_rows as classify_base_rows,
    read_jsonl,
    render_text,
    write_jsonl,
)
from .classify_next_noun_batch import classify_batch_row


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run the established classifier, then the verified NOUN batch on leftovers."""

    result = classify_base_rows(rows)
    enriched: list[dict[str, Any]] = []
    for row in result:
        if str(row.get("mismatch_classification")) != UNCLASSIFIED:
            enriched.append(row)
            continue
        classification, rationale = classify_batch_row(row)
        if classification == UNCLASSIFIED:
            enriched.append(row)
            continue
        enriched.append(
            {
                **row,
                "mismatch_classification": classification,
                "classification_rationale": rationale,
            }
        )
    return enriched


def classify_file(
    input_path: Path = DEFAULT_INPUT,
    *,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    rows = classify_rows(read_jsonl(input_path))
    write_jsonl(jsonl_path, rows)
    summary = build_summary(rows)
    summary.update(
        {
            "classifier": "base_plus_verified_noun_batch",
            "input": str(input_path),
            "jsonl": str(jsonl_path),
            "summary": str(summary_path),
            "text": str(text_path),
        }
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Klassificera SAOL–SALDO-paradigmskillnader med verifierad NOUN-batch"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = classify_file(
        args.input,
        jsonl_path=args.jsonl,
        summary_path=args.summary,
        text_path=args.text,
    )
    print(f"Paradigmmismatchposter: {summary['mismatch_records']}")
    print(f"Klassificerade: {summary['classified_records']}")
    print(f"Oklassificerade: {summary['unclassified_records']}")
    for name, count in summary["classification_counts"].items():
        print(f"{name}: {count}")
    print(f"Oklassificerade strukturer: {len(summary['unclassified_groups'])}")
    print(f"Text: {summary['text']}")
    print(f"JSONL: {summary['jsonl']}")


if __name__ == "__main__":
    main()
