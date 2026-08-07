from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical_direct_forms import canonical_record_forms
from .compare_sources import _build_form_index, read_saldo
from .jsonl import read_jsonl
from .validate_direct_forms import (
    DEFAULT_JSONL,
    DEFAULT_SALDO,
    DEFAULT_SAOL,
    DEFAULT_SUMMARY,
    _analysis_forms,
    _form_status,
    select_direct_match,
    write_jsonl,
)


def canonical_validation_row(
    record: dict[str, Any],
    match_method: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_forms = canonical_record_forms(record)
    saldo_forms = {
        form
        for analysis in analyses
        for form in _analysis_forms(analysis)
    }
    status = _form_status(generated_forms, saldo_forms, bool(generated_forms))
    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "lemma": str(record.get("normaliserat_ord") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "upos": str(record.get("upos") or "").upper(),
        "ordkl": str(record.get("ordkl") or ""),
        "notation": str(record.get("text") or ""),
        "match_method": match_method,
        "generator": "canonical_by_word_class",
        "saldo_ids": sorted({str(analysis["id"]) for analysis in analyses}),
        "saldo_lemmas": sorted(
            {str(lemma) for analysis in analyses for lemma in analysis["lemmas"]},
            key=str.casefold,
        ),
        "generated_forms": sorted(generated_forms, key=str.casefold),
        "saldo_forms": sorted(saldo_forms, key=str.casefold),
        "missing_from_saol": sorted(saldo_forms - generated_forms, key=str.casefold),
        "extra_from_saol": sorted(generated_forms - saldo_forms, key=str.casefold),
        "status": status,
    }


def revalidate_direct_forms(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    rows: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            continue
        method, analyses = selected
        rows.append(canonical_validation_row(record, method, analyses))

    rows.sort(key=lambda row: (str(row["status"]), str(row["lemma"]).casefold()))
    write_jsonl(jsonl_path, rows)

    status_counts = Counter(str(row["status"]) for row in rows)
    upos_status_counts: dict[str, Counter[str]] = {}
    for row in rows:
        upos_status_counts.setdefault(str(row["upos"]), Counter())[str(row["status"])] += 1

    summary = {
        "saol": str(saol_path),
        "saldo": str(saldo_path),
        "generator": "canonical_by_word_class",
        "matched_records": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "upos_status_counts": {
            upos: dict(sorted(counts.items()))
            for upos, counts in sorted(upos_status_counts.items())
        },
        "jsonl": str(jsonl_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Revalidate direct SAOL-SALDO matches with canonical word-class generators"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary = revalidate_direct_forms(args.saol, args.saldo, args.jsonl, args.summary)
    print(f"Direktmatchade poster: {summary['matched_records']}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Detaljer: {summary['jsonl']}")
    print(f"Summering: {args.summary}")


if __name__ == "__main__":
    main()
