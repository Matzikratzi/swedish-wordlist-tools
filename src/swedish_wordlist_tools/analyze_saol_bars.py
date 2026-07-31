from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("reports/saol14-unmatched-analysis.jsonl")
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-unmatched-saol-bars.jsonl")
DEFAULT_CSV = Path("reports/saol14-unmatched-saol-bars.csv")
DEFAULT_SUMMARY = Path("reports/saol14-unmatched-saol-bars-summary.json")


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def compact_word(value: str) -> str:
    return "".join(char for char in _normalise(value) if char.isalpha())


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or "")


def _stycke_values(value: Any, *, key: str = "") -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if str(child_key).casefold() == "stycke" and isinstance(child_value, str):
                result.append(child_value)
            else:
                result.extend(_stycke_values(child_value, key=str(child_key)))
    elif isinstance(value, list):
        for child in value:
            result.extend(_stycke_values(child, key=key))
    return result


def extract_bar_candidates(record: dict[str, Any]) -> list[str]:
    """Return unique SAOL stycke strings containing one or more lodstreck."""
    values = _stycke_values(record)
    direct = record.get("stycke")
    if isinstance(direct, str):
        values.insert(0, direct)

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = unicodedata.normalize("NFC", value.strip())
        if "|" not in value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def split_bar_candidate(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def classify_candidate(lemma: str, value: str) -> tuple[str, list[str]]:
    parts = split_bar_candidate(value)
    if len(parts) < 2:
        return "invalid_saol_bar", parts
    if compact_word("".join(parts)) == compact_word(lemma):
        return "saol_bar_matches_lemma", parts
    return "saol_bar_does_not_match_lemma", parts


def build_saol_indexes(
    records: Iterable[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_lemma: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        record_id = _record_id(record)
        if record_id:
            by_id[record_id].append(record)
        lemma = compact_word(str(record.get("normaliserat_ord", "")))
        if lemma:
            by_lemma[lemma].append(record)
    return dict(by_id), dict(by_lemma)


def _source_records(
    row: dict[str, Any],
    by_id: dict[str, list[dict[str, Any]]],
    by_lemma: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    record_id = str(row.get("record_id", ""))
    if record_id and record_id in by_id:
        return by_id[record_id]
    return by_lemma.get(compact_word(str(row.get("lemma", ""))), [])


def analyse_rows(
    rows: Iterable[dict[str, Any]],
    by_id: dict[str, list[dict[str, Any]]],
    by_lemma: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    result: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in rows:
        if row.get("analysis_reason") != "no_candidate":
            continue

        lemma = str(row.get("lemma", ""))
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in _source_records(row, by_id, by_lemma):
            for value in extract_bar_candidates(record):
                if value in seen:
                    continue
                seen.add(value)
                reason, parts = classify_candidate(lemma, value)
                candidates.append(
                    {
                        "stycke": value,
                        "parts": parts,
                        "compact_parts": [compact_word(part) for part in parts],
                        "reason": reason,
                        "source_record_id": _record_id(record),
                    }
                )

        matching = [
            candidate
            for candidate in candidates
            if candidate["reason"] == "saol_bar_matches_lemma"
        ]
        if len(matching) == 1:
            reason = "unique_saol_bar_split"
        elif len(matching) > 1:
            reason = "multiple_saol_bar_splits"
        elif candidates:
            reason = "saol_bar_does_not_match_lemma"
        else:
            reason = "no_saol_bar"
        counts[reason] += 1

        output = dict(row)
        output["saol_bar_reason"] = reason
        output["saol_bar_candidates"] = candidates
        output["saol_bar_splits"] = matching
        result.append(output)

    return result, dict(sorted(counts.items()))


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["lemma", "upos", "ordkl", "saol_bar_reason", "stycke", "parts"],
        )
        writer.writeheader()
        for row in rows:
            matches = row.get("saol_bar_splits", [])
            writer.writerow(
                {
                    "lemma": row.get("lemma", ""),
                    "upos": row.get("upos", ""),
                    "ordkl": row.get("ordkl", ""),
                    "saol_bar_reason": row.get("saol_bar_reason", ""),
                    "stycke": " | ".join(item["stycke"] for item in matches),
                    "parts": " | ".join(" + ".join(item["parts"]) for item in matches),
                }
            )


def analyse_saol_bars(
    input_path: Path = DEFAULT_INPUT,
    saol_path: Path = DEFAULT_SAOL,
    jsonl_path: Path = DEFAULT_JSONL,
    csv_path: Path = DEFAULT_CSV,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    by_id, by_lemma = build_saol_indexes(read_jsonl(saol_path))
    rows, counts = analyse_rows(read_jsonl(input_path), by_id, by_lemma)
    rows.sort(key=lambda row: str(row.get("lemma", "")).casefold())

    _write_jsonl(jsonl_path, rows)
    _write_csv(csv_path, rows)

    summary: dict[str, Any] = {
        "input": str(input_path),
        "saol": str(saol_path),
        "records": len(rows),
        "saol_records_by_id": sum(len(records) for records in by_id.values()),
        "saol_lemma_keys": len(by_lemma),
        "counts": counts,
        "jsonl": str(jsonl_path),
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
        description="Analyse unmatched SAOL compounds using explicit lodstreck in stycke"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_saol_bars(
        args.input,
        args.saol,
        args.jsonl,
        args.csv,
        args.summary,
    )
    print(f"Analyserade no_candidate-poster: {summary['records']}")
    for reason, count in summary["counts"].items():
        print(f"{reason}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"CSV: {summary['csv']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
