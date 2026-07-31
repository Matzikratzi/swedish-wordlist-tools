from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .analyze_saol_bars import compact_lemma, compact_word
from .jsonl import read_jsonl
from .saldo import SaldoAnalysis, SaldoWordForm, read_saldo_analyses

DEFAULT_INPUT = Path("reports/saol14-unmatched-saol-bars.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSONL = Path("reports/saol14-compound-heads.jsonl")
DEFAULT_CSV = Path("reports/saol14-compound-heads.csv")
DEFAULT_SUMMARY = Path("reports/saol14-compound-heads-summary.json")


@dataclass(frozen=True)
class HeadCandidate:
    analysis: SaldoAnalysis
    matched_forms: tuple[SaldoWordForm, ...] = ()


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
) -> tuple[dict[str, list[HeadCandidate]], dict[str, list[HeadCandidate]]]:
    """Build separate exact lemma and usable-word-form indexes.

    Word-form entries retain the matching SALDO WordForm records and their MSD
    values. Exact lemmas still have priority when they are compatible with the
    SAOL word class. If exact lemmas exist but none is compatible, a compatible
    exact word form may be used as a fallback.
    """
    lemma_index: dict[str, list[HeadCandidate]] = defaultdict(list)
    form_parts: dict[str, dict[tuple[str, str, tuple[str, ...]], tuple[SaldoAnalysis, list[SaldoWordForm]]]] = defaultdict(dict)
    seen_analyses: set[tuple[str, str, tuple[str, ...]]] = set()

    for analyses in saldo.values():
        for analysis in analyses:
            marker = analysis_marker(analysis)
            if marker in seen_analyses:
                continue
            seen_analyses.add(marker)

            for key in {exact_key(lemma) for lemma in analysis.lemmas} - {""}:
                lemma_index[key].append(HeadCandidate(analysis))

            for word_form in analysis.word_forms:
                if not usable_form(word_form.written_form):
                    continue
                key = exact_key(word_form.written_form)
                if not key:
                    continue
                if marker not in form_parts[key]:
                    form_parts[key][marker] = (analysis, [])
                form_parts[key][marker][1].append(word_form)

    form_index = {
        key: [HeadCandidate(analysis, tuple(forms)) for analysis, forms in entries.values()]
        for key, entries in form_parts.items()
    }
    return dict(lemma_index), form_index


def recovered_parts(row: dict[str, Any], split: dict[str, Any]) -> tuple[str, str] | None:
    parts = split.get("compact_parts") or []
    if len(parts) < 2:
        return None
    target = compact_lemma(str(row.get("lemma", "")))
    left = "".join(str(part) for part in parts[:-1])
    if not target.startswith(left) or len(left) >= len(target):
        return None
    return left, target[len(left) :]


def candidate_dict(candidate: HeadCandidate | SaldoAnalysis) -> dict[str, Any]:
    if isinstance(candidate, SaldoAnalysis):
        candidate = HeadCandidate(candidate)
    analysis = candidate.analysis
    result = {
        "id": analysis.entry_id,
        "upos": analysis.upos,
        "lemmas": sorted(analysis.lemmas, key=str.casefold),
        "forms": sorted((form for form in analysis.forms if usable_form(form)), key=str.casefold),
    }
    if candidate.matched_forms:
        result["matched_word_forms"] = [
            {"written_form": form.written_form, "msd": str(form.msd)}
            for form in candidate.matched_forms
        ]
    return result


def _is_participle(form: SaldoWordForm) -> bool:
    msd = form.msd.casefold().replace("-", "_")
    return msd.startswith("pres_part") or msd.startswith("pret_part")


def _compatible_with_upos(candidate: HeadCandidate, upos: str) -> bool:
    if upos and candidate.analysis.upos == upos:
        return True
    return upos == "ADJ" and any(_is_participle(form) for form in candidate.matched_forms)


def _select_candidates(
    key: str,
    upos: str,
    lemma_index: dict[str, list[HeadCandidate]],
    form_index: dict[str, list[HeadCandidate]],
) -> tuple[list[HeadCandidate], bool]:
    """Choose candidates while preserving lemma-first matching.

    Compatible exact lemmas always win. If exact lemmas exist but all have an
    incompatible word class, a compatible exact word-form match is preferred.
    This lets an SAOL adjective such as ``framkallande`` match the participial
    WordForm under the SALDO verb ``framkalla`` instead of being blocked by the
    unrelated noun lemma ``framkallande``.
    """
    lemma_candidates = lemma_index.get(key, [])
    compatible_lemmas = [candidate for candidate in lemma_candidates if _compatible_with_upos(candidate, upos)]
    if compatible_lemmas:
        return compatible_lemmas, True

    form_candidates = form_index.get(key, [])
    compatible_forms = [candidate for candidate in form_candidates if _compatible_with_upos(candidate, upos)]
    if compatible_forms:
        return compatible_forms, True

    if lemma_candidates:
        return lemma_candidates, False
    return form_candidates, False


def analyse_row(
    row: dict[str, Any],
    lemma_index: dict[str, list[HeadCandidate]],
    form_index: dict[str, list[HeadCandidate]],
) -> dict[str, Any]:
    result = dict(row)
    splits = row.get("saol_bar_splits", [])
    if row.get("saol_bar_reason") != "unique_saol_bar_split" or len(splits) != 1:
        result.update(head_match_reason="not_unique_saol_bar_split", compound_left="", compound_head="", head_candidates=[])
        return result

    recovered = recovered_parts(row, splits[0])
    if recovered is None:
        result.update(head_match_reason="cannot_recover_head", compound_left="", compound_head="", head_candidates=[])
        return result

    left, head = recovered
    upos = str(row.get("upos", "")).upper()
    key = exact_key(head)
    chosen, compatible = _select_candidates(key, upos, lemma_index, form_index)

    unique: list[HeadCandidate] = []
    seen = set()
    for candidate in chosen:
        marker = analysis_marker(candidate.analysis)
        if marker not in seen:
            seen.add(marker)
            unique.append(candidate)

    if not unique:
        reason = "head_not_in_saldo"
    elif compatible and len(unique) == 1:
        reason = "unique_head_same_upos"
    elif compatible:
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


def analyse_rows(rows: Iterable[dict[str, Any]], lemma_index, form_index) -> list[dict[str, Any]]:
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
                "lemma": row.get("lemma", ""), "upos": row.get("upos", ""),
                "compound_left": row.get("compound_left", ""), "compound_head": row.get("compound_head", ""),
                "head_match_reason": row.get("head_match_reason", ""),
                "candidate_ids": " | ".join(candidate.get("id", "") for candidate in candidates),
                "candidate_lemmas": " | ".join(", ".join(candidate.get("lemmas", [])) for candidate in candidates),
            })


def analyse_compound_heads(input_path: Path = DEFAULT_INPUT, saldo_path: Path = DEFAULT_SALDO,
                           jsonl_path: Path = DEFAULT_JSONL, csv_path: Path = DEFAULT_CSV,
                           summary_path: Path = DEFAULT_SUMMARY) -> dict[str, Any]:
    lemma_index, form_index = build_head_indexes(read_saldo_analyses(saldo_path))
    rows = analyse_rows(read_jsonl(input_path), lemma_index, form_index)
    rows.sort(key=lambda row: (str(row.get("head_match_reason", "")), str(row.get("lemma", "")).casefold()))
    counts = Counter(str(row.get("head_match_reason", "")) for row in rows)
    write_jsonl(jsonl_path, rows)
    write_csv(csv_path, rows)
    summary = {"input": str(input_path), "saldo": str(saldo_path), "records": len(rows),
               "counts": dict(sorted(counts.items())), "jsonl": str(jsonl_path), "csv": str(csv_path)}
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
