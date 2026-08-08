from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .classify_form_mismatches import (
    SALDO_COMPETING_GENDER_AND_FULL_PLURAL,
    UNCLASSIFIED,
    classify_row,
)

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-competing-gender-plural-classification.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-competing-gender-plural-classification-summary.json")


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def classify_competing_gender_plural(row: dict[str, Any]) -> tuple[str, str]:
    """Expose the verified +et vs common-gender+full-plural class as an audit.

    The main mismatch classifier is the single source of truth.  This helper
    deliberately returns only its one target class so the standalone audit and
    the production classification cannot drift apart again.
    """

    classification, rationale = classify_row(row)
    if classification == SALDO_COMPETING_GENDER_AND_FULL_PLURAL:
        return classification, rationale
    return UNCLASSIFIED, "not_competing_gender_and_full_plural"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def analyse_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    plural_types: Counter[str] = Counter()
    for row in rows:
        classification, rationale = classify_competing_gender_plural(row)
        if classification == UNCLASSIFIED:
            continue
        missing = _casefolded(row.get("missing_from_saol", ()))
        lemma = str(row.get("lemma", "")).casefold()
        plural_type = "-ar" if lemma + "ar" in missing else "-er"
        plural_types[plural_type] += 1
        matches.append({
            **row,
            "mismatch_classification": classification,
            "classification_rationale": rationale,
            "competing_plural_type": plural_type,
        })
    return {
        "classification": SALDO_COMPETING_GENDER_AND_FULL_PLURAL,
        "records": len(matches),
        "plural_type_counts": dict(sorted(plural_types.items())),
        "rows": matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit exact +et vs common-gender+full-plural SAOL–SALDO differences")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary = analyse_rows(read_jsonl(args.input))
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.jsonl.open("w", encoding="utf-8") as handle:
        for row in summary["rows"]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    public_summary = {key: value for key, value in summary.items() if key != "rows"}
    public_summary.update({"input": str(args.input), "jsonl": str(args.jsonl)})
    args.summary.write_text(json.dumps(public_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Klassificerade kandidater: {summary['records']}")
    for plural_type, count in summary["plural_type_counts"].items():
        print(f"{plural_type}: {count}")
    print(f"JSONL: {args.jsonl}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
