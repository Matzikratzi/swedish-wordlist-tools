from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saldo import SaldoAnalysis, read_saldo_analyses

DEFAULT_INPUT = Path("reports/saol14-only.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSONL = Path("reports/saol14-unmatched-analysis.jsonl")
DEFAULT_CSV = Path("reports/saol14-unmatched-analysis.csv")
DEFAULT_SUMMARY = Path("reports/saol14-unmatched-analysis-summary.json")


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _separator_key(value: str) -> str:
    return "".join(character for character in _normalise(value) if character.isalnum())


def _diacritic_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _separator_key(value))
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _deletion_keys(value: str) -> set[str]:
    key = _separator_key(value)
    return {key[:index] + key[index + 1 :] for index in range(len(key))}


def _analysis_marker(analysis: SaldoAnalysis) -> tuple[str, str, tuple[str, ...]]:
    return (
        analysis.entry_id,
        analysis.upos,
        tuple(sorted(analysis.lemmas, key=str.casefold)),
    )


def _candidate(analysis: SaldoAnalysis, matched_by: str) -> dict[str, Any]:
    return {
        "id": analysis.entry_id,
        "upos": analysis.upos,
        "lemmas": sorted(analysis.lemmas, key=str.casefold),
        "matched_by": matched_by,
    }


def _deduplicate(analyses: Iterable[SaldoAnalysis]) -> list[SaldoAnalysis]:
    result: list[SaldoAnalysis] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for analysis in analyses:
        marker = _analysis_marker(analysis)
        if marker not in seen:
            seen.add(marker)
            result.append(analysis)
    return result


def _classify_candidates(
    candidates: Iterable[SaldoAnalysis],
    saol_upos: str,
    same_pos_reason: str,
    other_pos_reason: str,
) -> tuple[str, list[SaldoAnalysis]] | None:
    unique = _deduplicate(candidates)
    if not unique:
        return None
    same_pos = [candidate for candidate in unique if saol_upos and candidate.upos == saol_upos]
    if same_pos:
        return same_pos_reason, same_pos
    return other_pos_reason, unique


def build_indexes(
    saldo: dict[str, list[SaldoAnalysis]],
) -> dict[str, dict[str, list[SaldoAnalysis]]]:
    indexes: dict[str, dict[str, list[SaldoAnalysis]]] = {
        "forms": defaultdict(list),
        "separator": defaultdict(list),
        "diacritic": defaultdict(list),
        "deletion": defaultdict(list),
    }
    seen_analyses: set[tuple[str, str, tuple[str, ...]]] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            marker = _analysis_marker(analysis)
            if marker in seen_analyses:
                continue
            seen_analyses.add(marker)
            values = set(analysis.lemmas) | set(analysis.forms)
            for value in values:
                indexes["forms"][_normalise(value)].append(analysis)
                indexes["separator"][_separator_key(value)].append(analysis)
                indexes["diacritic"][_diacritic_key(value)].append(analysis)
                for deletion_key in _deletion_keys(value):
                    indexes["deletion"][deletion_key].append(analysis)
    return {name: dict(index) for name, index in indexes.items()}


def analyse_row(
    row: dict[str, Any],
    saldo: dict[str, list[SaldoAnalysis]],
    indexes: dict[str, dict[str, list[SaldoAnalysis]]],
) -> dict[str, Any]:
    lemma = str(row.get("lemma", ""))
    upos = str(row.get("upos", "")).upper()
    lemma_key = _normalise(lemma)

    checks: list[tuple[Iterable[SaldoAnalysis], str, str, str]] = [
        (saldo.get(lemma_key, []), "lemma_same_upos", "lemma_upos_mismatch", "lemma"),
        (
            indexes["forms"].get(lemma_key, []),
            "wordform_same_upos",
            "wordform_upos_mismatch",
            "wordform",
        ),
        (
            indexes["separator"].get(_separator_key(lemma), []),
            "separator_difference_same_upos",
            "separator_difference_upos_mismatch",
            "separator",
        ),
        (
            indexes["diacritic"].get(_diacritic_key(lemma), []),
            "diacritic_difference_same_upos",
            "diacritic_difference_upos_mismatch",
            "diacritic",
        ),
    ]

    for candidates, same_reason, other_reason, matched_by in checks:
        classified = _classify_candidates(candidates, upos, same_reason, other_reason)
        if classified is not None:
            reason, chosen = classified
            result = dict(row)
            result["analysis_reason"] = reason
            result["candidates"] = [_candidate(candidate, matched_by) for candidate in chosen]
            return result

    single_edit_candidates: list[SaldoAnalysis] = []
    compact = _separator_key(lemma)
    for deletion_key in _deletion_keys(lemma):
        single_edit_candidates.extend(indexes["deletion"].get(deletion_key, []))
    single_edit_candidates.extend(indexes["deletion"].get(compact, []))
    classified = _classify_candidates(
        single_edit_candidates,
        upos,
        "single_edit_same_upos",
        "single_edit_upos_mismatch",
    )
    result = dict(row)
    if classified is None:
        result["analysis_reason"] = "no_candidate"
        result["candidates"] = []
    else:
        reason, chosen = classified
        result["analysis_reason"] = reason
        result["candidates"] = [_candidate(candidate, "single_edit") for candidate in chosen[:20]]
        if len(chosen) > 20:
            result["candidate_count"] = len(chosen)
    return result


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "lemma",
        "upos",
        "ordkl",
        "notation",
        "analysis_reason",
        "candidate_lemmas",
        "candidate_upos",
        "candidate_ids",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            candidates = row.get("candidates", [])
            writer.writerow(
                {
                    "lemma": row.get("lemma", ""),
                    "upos": row.get("upos", ""),
                    "ordkl": row.get("ordkl", ""),
                    "notation": row.get("notation", ""),
                    "analysis_reason": row.get("analysis_reason", ""),
                    "candidate_lemmas": " | ".join(
                        ", ".join(candidate.get("lemmas", [])) for candidate in candidates
                    ),
                    "candidate_upos": " | ".join(candidate.get("upos", "") for candidate in candidates),
                    "candidate_ids": " | ".join(candidate.get("id", "") for candidate in candidates),
                }
            )


def analyse_unmatched(
    input_path: Path = DEFAULT_INPUT,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    csv_path: Path = DEFAULT_CSV,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    saldo = read_saldo_analyses(saldo_path)
    indexes = build_indexes(saldo)
    rows = [analyse_row(row, saldo, indexes) for row in read_jsonl(input_path)]
    rows.sort(key=lambda row: (str(row["analysis_reason"]), str(row.get("lemma", "")).casefold()))

    counts = Counter(str(row["analysis_reason"]) for row in rows)
    _write_jsonl(jsonl_path, rows)
    _write_csv(csv_path, rows)
    summary: dict[str, Any] = {
        "input": str(input_path),
        "saldo": str(saldo_path),
        "records": len(rows),
        "counts": dict(sorted(counts.items())),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explain why SAOL entries did not match SALDO")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_unmatched(args.input, args.saldo, args.jsonl, args.csv, args.summary)
    print(f"Analyserade omatchade SAOL-poster: {summary['records']}")
    for reason, count in summary["counts"].items():
        print(f"{reason}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"CSV: {summary['csv']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
