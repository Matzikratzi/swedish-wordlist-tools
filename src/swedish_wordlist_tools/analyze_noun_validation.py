from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSON = Path("reports/saol14-remaining-noun-patterns.json")
DEFAULT_TSV = Path("reports/saol14-remaining-noun-patterns.tsv")

_REMAINING_STATUSES = {
    "saol_forms_are_subset",
    "form_set_mismatch",
    "saol_pattern_unsupported",
    "saol_zero_plural_differs_from_saldo",
}


def analyse_rows(rows: Iterable[dict[str, Any]], sample_size: int = 12) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    status_counts: Counter[str] = Counter()

    for row in rows:
        if str(row.get("upos", "")) != "NOUN":
            continue
        status = str(row.get("status", ""))
        if status not in _REMAINING_STATUSES:
            continue
        notation = str(row.get("notation", ""))
        grouped[notation].append(row)
        status_counts[status] += 1

    patterns: list[dict[str, Any]] = []
    for notation, items in grouped.items():
        counts = Counter(str(item.get("status", "")) for item in items)
        extra_forms = Counter(
            form
            for item in items
            for form in item.get("extra_from_saol", [])
        )
        missing_forms = Counter(
            form
            for item in items
            for form in item.get("missing_from_saol", [])
        )
        patterns.append({
            "notation": notation,
            "records": len(items),
            "status_counts": dict(sorted(counts.items())),
            "sample_lemmas": sorted(
                {str(item.get("lemma", "")) for item in items}, key=str.casefold
            )[:sample_size],
            "common_extra_forms": extra_forms.most_common(10),
            "common_missing_forms": missing_forms.most_common(10),
        })

    patterns.sort(key=lambda item: (-int(item["records"]), str(item["notation"]).casefold()))
    return {
        "noun_records_remaining": sum(status_counts.values()),
        "status_counts": dict(sorted(status_counts.items())),
        "distinct_notations": len(patterns),
        "patterns": patterns,
    }


def write_report(report: dict[str, Any], json_path: Path, tsv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow([
            "records", "notation", "exact", "subset", "mismatch", "unsupported",
            "zero_plural_difference", "sample_lemmas",
        ])
        for pattern in report["patterns"]:
            counts = pattern["status_counts"]
            writer.writerow([
                pattern["records"],
                pattern["notation"],
                counts.get("exact_form_set", 0),
                counts.get("saol_forms_are_subset", 0),
                counts.get("form_set_mismatch", 0),
                counts.get("saol_pattern_unsupported", 0),
                counts.get("saol_zero_plural_differs_from_saldo", 0),
                ", ".join(pattern["sample_lemmas"]),
            ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank remaining SAOL noun notations from the direct-form validation report"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--sample-size", type=int, default=12)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = analyse_rows(read_jsonl(args.input), sample_size=args.sample_size)
    write_report(report, args.json, args.tsv)
    print(f"Återstående substantivposter: {report['noun_records_remaining']}")
    print(f"Unika notationer: {report['distinct_notations']}")
    print(f"JSON: {args.json}")
    print(f"TSV: {args.tsv}")


if __name__ == "__main__":
    main()
