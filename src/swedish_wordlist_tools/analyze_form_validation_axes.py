from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-form-validation-axes.jsonl")
DEFAULT_TEXT = Path("reports/saol14-form-validation-axes.txt")
DEFAULT_SUMMARY = Path("reports/saol14-form-validation-axes-summary.json")

GOOD_PARADIGM_STATUSES = frozenset({
    "exact_form_set",
    "exact_form_set_case_difference",
    "saol_forms_are_subset",
})


def classify_axes(row: dict[str, Any]) -> tuple[str, str, str]:
    """Return (coverage_status, paradigm_status, paradigm_reason).

    Coverage answers whether all materialized SAOL headings are represented in SALDO.
    Paradigm status answers whether the forms of headings that *are* represented agree.
    The two dimensions are deliberately independent.

    For fully covered variant articles, paradigm comparison is article-level: the
    union of all SAOL variant forms is compared with the union of all matched
    SALDO forms. Per-heading validation remains diagnostic, but must not turn an
    article-level exact match into a mismatch merely because shared forms are
    assigned to a different lemma/heading in SALDO.
    """

    variants = list(row.get("variant_validation") or [])
    raw_status = str(row.get("status") or "")

    if not variants:
        coverage = "not_applicable"
        if raw_status == "form_set_mismatch":
            return coverage, "form_set_mismatch", "non_variant_form_difference"
        return coverage, raw_status, raw_status

    missing = [v for v in variants if v.get("status") == "variant_missing_in_saldo"]
    present = [v for v in variants if v.get("status") != "variant_missing_in_saldo"]

    if not missing:
        coverage = "full"
    elif not present:
        coverage = "missing"
    else:
        coverage = "partial"

    # When every SAOL heading is represented in SALDO, the correct paradigm
    # object is the whole article/lexeme. Shared surface forms may legitimately
    # be attached to a different heading in SALDO than in SAOL. The already
    # materialized top-level status compares exactly these article unions.
    if coverage == "full" and raw_status:
        if raw_status == "exact_form_set":
            return coverage, raw_status, "article_union_exact"
        if raw_status == "exact_form_set_case_difference":
            return coverage, raw_status, "article_union_exact_ignoring_case"
        if raw_status == "saol_forms_are_subset":
            return coverage, raw_status, "article_union_saol_subset"
        if raw_status == "form_set_mismatch":
            return coverage, raw_status, "article_union_form_difference"

    primary_present = [
        v for v in present if str(v.get("heading_type") or "") == "primary"
    ]
    alternative_present = [
        v for v in present if str(v.get("heading_type") or "") == "alternative"
    ]

    statuses = [str(v.get("status") or "") for v in present]
    if not statuses:
        paradigm = "not_comparable"
        reason = "no_variant_present_in_saldo"
    elif any(status == "form_set_mismatch" for status in statuses):
        paradigm = "form_set_mismatch"
        if any(str(v.get("status") or "") == "form_set_mismatch" for v in primary_present):
            reason = "primary_paradigm_difference"
        elif any(str(v.get("status") or "") == "form_set_mismatch" for v in alternative_present):
            reason = "alternative_paradigm_difference"
        else:
            reason = "variant_paradigm_difference"
    elif all(status == "exact_form_set" for status in statuses):
        paradigm = "exact_form_set"
        reason = "all_present_variants_exact"
    elif all(status in {"exact_form_set", "exact_form_set_case_difference"} for status in statuses):
        paradigm = "exact_form_set_case_difference"
        reason = "all_present_variants_exact_ignoring_case"
    elif all(status in GOOD_PARADIGM_STATUSES for status in statuses):
        paradigm = "saol_forms_are_subset"
        reason = "at_least_one_present_variant_is_saol_subset"
    else:
        paradigm = "other"
        reason = "mixed_present_variant_statuses"

    return coverage, paradigm, reason


def analyze_rows(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output: list[dict[str, Any]] = []
    coverage_counts: Counter[str] = Counter()
    paradigm_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    cross_counts: Counter[str] = Counter()

    for row in rows:
        coverage, paradigm, reason = classify_axes(row)
        item = dict(row)
        item["coverage_status"] = coverage
        item["paradigm_status"] = paradigm
        item["paradigm_reason"] = reason
        output.append(item)
        coverage_counts[coverage] += 1
        paradigm_counts[paradigm] += 1
        reason_counts[reason] += 1
        cross_counts[f"{coverage} | {paradigm}"] += 1

    summary = {
        "rows": len(output),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "paradigm_status_counts": dict(sorted(paradigm_counts.items())),
        "paradigm_reason_counts": dict(sorted(reason_counts.items())),
        "coverage_paradigm_cross_counts": dict(sorted(cross_counts.items())),
    }
    return summary, output


def render(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "SAOL14 formvalidering: två oberoende axlar",
        "",
        "Varianttäckning:",
    ]
    lines.extend(
        f"  {count:6d}  {status}"
        for status, count in summary["coverage_status_counts"].items()
    )
    lines.extend(["", "Paradigm för varianter som finns i SALDO:"])
    lines.extend(
        f"  {count:6d}  {status}"
        for status, count in summary["paradigm_status_counts"].items()
    )
    lines.extend(["", "Korsning coverage | paradigm:"])
    lines.extend(
        f"  {count:6d}  {status}"
        for status, count in summary["coverage_paradigm_cross_counts"].items()
    )

    interesting = [
        row for row in rows
        if row["coverage_status"] != "not_applicable"
        and (row["coverage_status"] != "full" or row["paradigm_status"] == "form_set_mismatch")
    ]
    lines.extend(["", "Variantartiklar med ofullständig täckning eller paradigmskillnad:"])
    for row in interesting:
        lines.append(
            f"  {row.get('lemma')} ({row.get('record_id')}, homonr={row.get('homonym_number')}): "
            f"coverage={row['coverage_status']} paradigm={row['paradigm_status']} "
            f"reason={row['paradigm_reason']}"
        )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split SAOL/SALDO validation into coverage and paradigm axes")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary, rows = analyze_rows(read_jsonl(args.validation))
    write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary, rows), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Varianttäckning:")
    for key, value in summary["coverage_status_counts"].items():
        print(f"{key}: {value}")
    print("Paradigmstatus:")
    for key, value in summary["paradigm_status_counts"].items():
        print(f"{key}: {value}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
