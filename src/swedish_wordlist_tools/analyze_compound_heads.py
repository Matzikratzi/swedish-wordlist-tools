from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_saol_bars import compact_lemma, compact_word
from .jsonl import read_jsonl
from .saldo import SaldoAnalysis, read_saldo_analyses

DEFAULT_INPUT = Path("reports/saol14-unmatched-saol-bars.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSONL = Path("reports/saol14-compound-heads.jsonl")
DEFAULT_CSV = Path("reports/saol14-compound-heads.csv")
DEFAULT_SUMMARY = Path("reports/saol14-compound-heads-summary.json")


def exact_key(value: str) -> str:
    """Return the comparison key without removing Swedish diacritics."""
    return compact_word(value)


def usable_form(form: str) -> bool:
    """Exclude SALDO composition forms such as ``grund-`` and ``grunds-``."""
    return bool(form) and not form.rstrip().endswith("-")


def analysis_marker(analysis: SaldoAnalysis) -> tuple[str, str, tuple[str, ...]]:
    return analysis.entry_id, analysis.upos, tuple(sorted(analysis.lemmas, key=str.casefold))


def build_head_indexes(
    saldo: dict[str, list[SaldoAnalysis]],
) -> tuple[dict[str, list[SaldoAnalysis]], dict[str, list[SaldoAnalysis]]]:
    """Build separate exact lemma and usable-word-form indexes.

    Compound heads first match the lemma index. The word-form index is only a
    fallback when there is no exact lemma match. Matching is case-insensitive
    and ignores layout punctuation through ``compact_word``, while preserving
    Swedish letters and diacritics.
    """
    lemma_index: dict[str, list[SaldoAnalysis]] = defaultdict(list)
    form_index: dict[str, list[SaldoAnalysis]] = defaultdict(list)
    seen_analyses: set[tuple[str, str, tuple[str, ...]]] = set()

    for analyses in saldo.values():
        for analysis in analyses:
            marker = analysis_marker(analysis)
            if marker in seen_analyses:
                continue
            seen_analyses.add(marker)

            lemma_keys = {exact_key(lemma) for lemma in analysis.lemmas}
            lemma_keys.discard("")
            for key in lemma_keys:
                lemma_index[key].append(analysis)

            form_keys = {
                exact_key(form)
                for form in analysis.forms
                if usable_form(form)
            }
            form_keys.discard("")
            for key in form_keys:
                form_index[key].append(analysis)

    return dict(lemma_index), dict(form_index)


def recovered_parts(row: dict[str, Any], split: dict[str, Any]) -> tuple[str, str] | None:
    parts = split.get("compact_parts") or []
    if len(parts) < 2:
        return None

    target = compact_lemma(str(row.get("lemma", "")))
    left = "".join(str(part) for part in parts[:-1])
    if not target.startswith(left) or len(left) >= len(target):
        return None
    return left, target[len(left) :]


def candidate_dict(analysis: SaldoAnalysis) -> dict[str, Any]:
    return {
        "id": analysis.entry_id,
        "upos": analysis.upos,
        "lemmas": sorted(analysis.lemmas, key=str.casefold),
        "forms": sorted((form for form in analysis.forms if usable_form(form)), key=str.casefold),
    }


def analyse_row(
    row: dict[str, Any],
    lemma_index: dict[str, list[SaldoAnalysis]],
    form_index: dict[str, list[SaldoAnalysis]],
) -> dict[str, Any]:
    result = dict(row)
    splits = row.get("saol_bar_splits", [])
    if row.get("saol_bar_reason") != "unique_saol_bar_split" or len(splits) != 1:
        result["head_match_reason"] = "not_unique_saol_bar_split"
        result["compound_left"] = ""
        result["compound_head"] = ""
        result["head_candidates"] = []
        return result

    recovered = recovered_parts(row, splits[0])
    if recovered is None:
        result["head_match_reason"] = "cannot_recover_head"
        result["compound_left"] = ""
        result["compound_head"] = ""
        result["head_candidates"] = []
        return result

    left, head = recovered
    upos = str(row.get("upos", "")).upper()
    key = exact_key(head)
    lemma_candidates = lemma_index.get(key, [])
    candidates = lemma_candidates if lemma_candidates else form_index.get(key, [])
    same_pos = [candidate for candidate in candidates if upos and candidate.upos == upos]
    chosen = same_pos if same_pos else candidates

    unique = []
    seen = set()
    for candidate in chosen:
        marker = analysis_marker(candidate)
        if marker not in seen:
            seen.add(marker)
            unique.append(candidate)

    if not unique:
        reason = "head_not_in_saldo"
    elif same_pos and len(unique) == 1:
        reason = "unique_head_same_upos"
    elif same_pos:
        reason = "multiple_heads_same_upos"
    elif len(unique) == 1:
        reason = "unique_head_upos_mismatch"
    else:
        reason = "multiple_heads_upos_mismatch"

    result["head_match_reason"] = reason
    result["compound_left"] = left
    result["compound_head"] = head
    result["head_candidates"] = [candidate_dict(candidate) for candidate in unique]
    return result


def analyse_rows(
    rows: Iterable[dict[str, Any]],
    lemma_index: dict[str, list[SaldoAnalysis]],
    form_index: dict[str, list[SaldoAnalysis]],
) -> list[dict[str, Any]]:
    return [analyse_row(row, lemma_index, form_index) for row in rows]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["lemma", "upos", "compound_left", "compound_head", "head_match_reason", "candidate_ids", "candidate_lemmas"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            candidates = row.get("head_candidates", [])
            writer.writerow({
                "lemma": row.get("lemma", ""),
                "upos": row.get("upos", ""),
                "compound_left": row.get("compound_left", ""),
                "compound_head": row.get("compound_head", ""),
                "head_match_reason": row.get("head_match_reason", ""),
                "candidate_ids": " | ".join(candidate.get("id", "") for candidate in candidates),
                "candidate_lemmas": " | ".join(", ".join(candidate.get("lemmas", [])) for candidate in candidates),
            })


def analyse_compound_heads(
    input_path: Path = DEFAULT_INPUT,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    csv_path: Path = DEFAULT_CSV,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    lemma_index, form_index = build_head_indexes(read_saldo_analyses(saldo_path))
    rows = analyse_rows(read_jsonl(input_path), lemma_index, form_index)
    rows.sort(key=lambda row: (str(row.get("head_match_reason", "")), str(row.get("lemma", "")).casefold()))
    counts = Counter(str(row.get("head_match_reason", "")) for row in rows)
    write_jsonl(jsonl_path, rows)
    write_csv(csv_path, rows)
    summary = {
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
    parser = argparse.ArgumentParser(description="Match the rightmost SAOL compound part exactly against SALDO")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_compound_heads(args.input, args.saldo, args.jsonl, args.csv, args.summary)
    print(f"Analyserade poster: {summary['records']}")
    for reason, count in summary["counts"].items():
        print(f"{reason}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"CSV: {summary['csv']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
