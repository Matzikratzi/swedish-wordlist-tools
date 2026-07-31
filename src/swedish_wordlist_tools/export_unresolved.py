from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_AMBIGUOUS = Path("reports/saol14-saldo-ambiguous.jsonl")
DEFAULT_COMPOUNDS = Path("reports/saol14-compound-heads.jsonl")
DEFAULT_JSON = Path("reports/saol14-unresolved.json")
DEFAULT_CSV = Path("reports/saol14-unresolved.csv")
DEFAULT_SUMMARY = Path("reports/saol14-unresolved-summary.json")

SOLVED_COMPOUND_REASONS = {"unique_head_same_upos"}


def _candidate_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("head_candidates", "saldo_analyses", "saldo_form_analyses"):
        candidates = row.get(key)
        if isinstance(candidates, list):
            return [candidate for candidate in candidates if isinstance(candidate, dict)]
    return []


def _candidate_values(candidates: Iterable[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for candidate in candidates:
        value = candidate.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if item)
        elif value:
            values.append(str(value))
    return sorted(set(values), key=str.casefold)


def _split_values(row: dict[str, Any]) -> list[str]:
    splits = row.get("saol_bar_splits")
    if not isinstance(splits, list):
        return []
    values: list[str] = []
    for split in splits:
        if not isinstance(split, dict):
            continue
        parts = split.get("parts")
        if isinstance(parts, list) and parts:
            values.append(" + ".join(str(part) for part in parts))
        elif split.get("stycke"):
            values.append(str(split["stycke"]))
    return values


def exploration_row(row: dict[str, Any], source_group: str) -> dict[str, Any]:
    candidates = _candidate_rows(row)
    lemma = str(row.get("lemma", ""))
    left = str(row.get("compound_left", ""))
    head = str(row.get("compound_head", ""))
    reason = str(row.get("head_match_reason") or row.get("reason") or "")

    return {
        "source_group": source_group,
        "problem_reason": reason,
        "lemma": lemma,
        "upos": str(row.get("upos", "")),
        "ordkl": str(row.get("ordkl", "")),
        "record_id": str(row.get("record_id", "")),
        "notation": str(row.get("notation", "")),
        "generated_forms": row.get("generated_forms", []),
        "saol_bar_reason": str(row.get("saol_bar_reason", "")),
        "saol_bar_splits": _split_values(row),
        "compound_left": left,
        "compound_head": head,
        "candidate_count": len(candidates),
        "candidate_ids": _candidate_values(candidates, "id"),
        "candidate_lemmas": _candidate_values(candidates, "lemmas"),
        "candidate_upos": _candidate_values(candidates, "upos"),
        "lemma_length": len(lemma),
        "compound_left_length": len(left),
        "compound_head_length": len(head),
        "compound_left_last": left[-1:] if left else "",
        "compound_head_first": head[:1] if head else "",
        "compound_head_last": head[-1:] if head else "",
    }


def collect_unresolved(
    ambiguous_rows: Iterable[dict[str, Any]],
    compound_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [exploration_row(row, "saldo_ambiguous") for row in ambiguous_rows]
    rows.extend(
        exploration_row(row, "compound")
        for row in compound_rows
        if str(row.get("head_match_reason", "")) not in SOLVED_COMPOUND_REASONS
    )
    rows.sort(
        key=lambda row: (
            str(row["source_group"]),
            str(row["problem_reason"]),
            str(row["lemma"]).casefold(),
        )
    )
    return rows


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    fields = [
        "source_group",
        "problem_reason",
        "lemma",
        "upos",
        "ordkl",
        "record_id",
        "notation",
        "saol_bar_reason",
        "saol_bar_splits",
        "compound_left",
        "compound_head",
        "candidate_count",
        "candidate_ids",
        "candidate_lemmas",
        "candidate_upos",
        "lemma_length",
        "compound_left_length",
        "compound_head_length",
        "compound_left_last",
        "compound_head_first",
        "compound_head_last",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            for field in (
                "saol_bar_splits",
                "candidate_ids",
                "candidate_lemmas",
                "candidate_upos",
            ):
                output[field] = " | ".join(str(value) for value in output[field])
            writer.writerow(output)


def export_unresolved(
    ambiguous_path: Path = DEFAULT_AMBIGUOUS,
    compounds_path: Path = DEFAULT_COMPOUNDS,
    json_path: Path = DEFAULT_JSON,
    csv_path: Path = DEFAULT_CSV,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    rows = collect_unresolved(read_jsonl(ambiguous_path), read_jsonl(compounds_path))
    write_json(json_path, rows)
    write_csv(csv_path, rows)

    reasons = Counter(str(row["problem_reason"]) for row in rows)
    groups = Counter(str(row["source_group"]) for row in rows)
    summary = {
        "ambiguous_input": str(ambiguous_path),
        "compound_input": str(compounds_path),
        "records": len(rows),
        "groups": dict(sorted(groups.items())),
        "reasons": dict(sorted(reasons.items())),
        "json": str(json_path),
        "csv": str(csv_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export only unresolved SAOL 14 records for pattern exploration"
    )
    parser.add_argument("--ambiguous", type=Path, default=DEFAULT_AMBIGUOUS)
    parser.add_argument("--compounds", type=Path, default=DEFAULT_COMPOUNDS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = export_unresolved(
        args.ambiguous,
        args.compounds,
        args.json,
        args.csv,
        args.summary,
    )
    print(f"Olösta SAOL-poster: {summary['records']}")
    for group, count in summary["groups"].items():
        print(f"{group}: {count}")
    print(f"JSON: {summary['json']}")
    print(f"CSV: {summary['csv']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
