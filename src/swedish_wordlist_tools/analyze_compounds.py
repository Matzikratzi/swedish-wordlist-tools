from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saldo import NON_STANDALONE_MSD, SaldoAnalysis, read_saldo_analyses

DEFAULT_INPUT = Path("reports/saol14-unmatched-analysis.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSONL = Path("reports/saol14-unmatched-compounds.jsonl")
DEFAULT_CSV = Path("reports/saol14-unmatched-compounds.csv")
DEFAULT_SUMMARY = Path("reports/saol14-unmatched-compounds-summary.json")

_SEPARATOR_RE = re.compile(r"[^\wåäöÅÄÖ]+", re.UNICODE)
_NON_STANDALONE_MSD = NON_STANDALONE_MSD


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def compact_word(value: str) -> str:
    """Return a lowercase letters-only comparison form."""
    return "".join(char for char in _normalise(value) if char.isalpha())


def _standalone_forms(analysis: SaldoAnalysis) -> set[str]:
    result = {compact_word(lemma) for lemma in analysis.lemmas}
    for form in analysis.word_forms:
        if form.msd.casefold() not in _NON_STANDALONE_MSD:
            result.add(compact_word(form.written_form))
    return {value for value in result if len(value) >= 2}


def _compound_stems(analysis: SaldoAnalysis) -> set[str]:
    result: set[str] = set()
    for form in analysis.word_forms:
        if form.msd.casefold() in {"cm", "sms"}:
            value = compact_word(form.written_form)
            if len(value) >= 2:
                result.add(value)
    return result


def build_compound_indexes(
    saldo: dict[str, list[SaldoAnalysis]],
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    """Return left-part stems, standalone right parts, and display labels."""
    left_parts: set[str] = set()
    right_parts: set[str] = set()
    labels: dict[str, set[str]] = defaultdict(set)

    seen: set[SaldoAnalysis] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            if analysis in seen:
                continue
            seen.add(analysis)
            lemmas = sorted(analysis.lemmas, key=str.casefold)
            label = "/".join(lemmas) if lemmas else analysis.entry_id

            standalone = _standalone_forms(analysis)
            stems = _compound_stems(analysis)
            right_parts.update(standalone)
            left_parts.update(stems)

            # Ordinary lemmas are also legitimate first parts in transparent compounds.
            for lemma in analysis.lemmas:
                compact = compact_word(lemma)
                if len(compact) >= 2:
                    left_parts.add(compact)

            for value in standalone | stems:
                labels[value].add(label)

    return left_parts, right_parts, dict(labels)


def find_compound_splits(
    word: str,
    left_parts: set[str],
    right_parts: set[str],
    *,
    min_part_length: int = 2,
) -> list[tuple[str, str]]:
    compact = compact_word(word)
    if len(compact) < min_part_length * 2:
        return []

    matches: list[tuple[str, str]] = []
    for split_at in range(min_part_length, len(compact) - min_part_length + 1):
        left = compact[:split_at]
        right = compact[split_at:]
        if left in left_parts and right in right_parts:
            matches.append((left, right))
    return matches


def classify_splits(splits: list[tuple[str, str]]) -> str:
    if not splits:
        return "no_compound_split"
    if len(splits) == 1:
        return "unique_compound_split"
    return "multiple_compound_splits"


def analyse_rows(
    rows: Iterable[dict[str, Any]],
    left_parts: set[str],
    right_parts: set[str],
    labels: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    result: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in rows:
        if row.get("analysis_reason") != "no_candidate":
            continue
        lemma = str(row.get("lemma", ""))
        splits = find_compound_splits(lemma, left_parts, right_parts)
        reason = classify_splits(splits)
        counts[reason] += 1

        output = dict(row)
        output["compound_reason"] = reason
        output["compact_lemma"] = compact_word(lemma)
        output["compound_splits"] = [
            {
                "left": left,
                "right": right,
                "left_analyses": sorted(labels.get(left, set()), key=str.casefold)[:20],
                "right_analyses": sorted(labels.get(right, set()), key=str.casefold)[:20],
            }
            for left, right in splits
        ]
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
            fieldnames=["lemma", "upos", "ordkl", "compound_reason", "splits"],
        )
        writer.writeheader()
        for row in rows:
            split_text = " | ".join(
                f"{split['left']} + {split['right']}"
                for split in row.get("compound_splits", [])
            )
            writer.writerow(
                {
                    "lemma": row.get("lemma", ""),
                    "upos": row.get("upos", ""),
                    "ordkl": row.get("ordkl", ""),
                    "compound_reason": row.get("compound_reason", ""),
                    "splits": split_text,
                }
            )


def analyse_unmatched_compounds(
    input_path: Path = DEFAULT_INPUT,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    csv_path: Path = DEFAULT_CSV,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    saldo = read_saldo_analyses(saldo_path)
    left_parts, right_parts, labels = build_compound_indexes(saldo)
    rows, counts = analyse_rows(read_jsonl(input_path), left_parts, right_parts, labels)

    rows.sort(key=lambda row: str(row.get("lemma", "")).casefold())
    _write_jsonl(jsonl_path, rows)
    _write_csv(csv_path, rows)

    summary: dict[str, Any] = {
        "input": str(input_path),
        "saldo": str(saldo_path),
        "records": len(rows),
        "left_part_index": len(left_parts),
        "right_part_index": len(right_parts),
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
        description="Analyse unmatched SAOL entries as possible SALDO-based compounds"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_unmatched_compounds(
        args.input,
        args.saldo,
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
