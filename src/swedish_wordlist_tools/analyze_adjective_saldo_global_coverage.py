from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _build_form_index, read_saldo

DEFAULT_MISMATCHES = Path("reports/saol14-adjective-mismatch-causes.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-adjective-saldo-global-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-saldo-global-coverage.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-saldo-global-coverage.jsonl")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def classify_global_presence(
    written_form: str,
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[dict[str, Any]]]:
    analyses = list(form_index.get(str(written_form or "").casefold(), ()))
    adjective = [analysis for analysis in analyses if analysis.get("upos") == "ADJ"]
    if adjective:
        return "found_in_other_saldo_adjective_analysis", adjective
    if analyses:
        return "only_non_adjective_saldo_match", analyses
    return "absent_from_all_saldo", []


def _review_category(status: str) -> str:
    return {
        "found_in_other_saldo_adjective_analysis": "saldo_alignment_problem",
        "only_non_adjective_saldo_match": "saldo_word_class_or_coverage_review",
        "absent_from_all_saldo": "saldo_coverage_or_saol_review",
    }[status]


def _linguistic_identity(
    row: dict[str, Any], form: dict[str, Any]
) -> tuple[str, str, str]:
    """Identify one linguistic mismatch independently of comparison-row identity."""

    return (
        str(row.get("lemma") or "").casefold(),
        str(form.get("slot") or ""),
        str(form.get("written_form") or "").casefold(),
    )


def _source_occurrence(row: dict[str, Any]) -> dict[str, str]:
    return {
        "record_id": str(row.get("record_id") or ""),
        "homonym_number": str(row.get("homonym_number") or ""),
        "match_method": str(row.get("match_method") or ""),
    }


def analyze_rows(
    rows: Iterable[dict[str, Any]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_rows = list(rows)
    raw_forms = sum(
        len(row.get("classified_missing_forms", ())) for row in source_rows
    )

    # Collapse across the complete report, not separately inside every row.
    # Several selected SALDO analyses or duplicate SAOL records can otherwise
    # produce the same visible linguistic case more than once.
    cases: dict[tuple[str, str, str], dict[str, Any]] = {}
    occurrences: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    first_row_index: dict[tuple[str, str, str], int] = {}

    for row_index, row in enumerate(source_rows):
        for form in row.get("classified_missing_forms", ()):
            identity = _linguistic_identity(row, form)
            if identity not in cases:
                cases[identity] = dict(form)
                first_row_index[identity] = row_index
            occurrence = _source_occurrence(row)
            if occurrence not in occurrences[identity]:
                occurrences[identity].append(occurrence)

    status_counts: Counter[str] = Counter()
    review_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    forms_by_row: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for identity, form in cases.items():
        lemma, _slot, _written_form = identity
        written_form = str(form.get("written_form") or "")
        status, analyses = classify_global_presence(written_form, form_index)
        review_category = _review_category(status)
        status_counts[status] += 1
        review_counts[review_category] += 1
        item = {
            **form,
            "global_saldo_status": status,
            "global_review_category": review_category,
            "source_occurrence_count": len(occurrences[identity]),
            "source_occurrences": occurrences[identity],
            "global_saldo_analyses": [
                {
                    "id": str(analysis.get("id") or ""),
                    "upos": str(analysis.get("upos") or ""),
                    "lemmas": sorted(
                        (str(value) for value in analysis.get("lemmas", ())),
                        key=str.casefold,
                    ),
                }
                for analysis in analyses
            ],
        }
        forms_by_row[first_row_index[identity]].append(item)
        if len(examples[status]) < 30:
            examples[status].append({
                "lemma": lemma,
                "form": written_form,
                "slot": form.get("slot"),
                "source_token": form.get("source_token"),
                "provenance": form.get("provenance"),
                "review_category": review_category,
                "source_occurrence_count": len(occurrences[identity]),
                "analyses": item["global_saldo_analyses"],
            })

    output_rows = [
        {**row, "classified_missing_forms": forms_by_row.get(index, [])}
        for index, row in enumerate(source_rows)
        if forms_by_row.get(index)
    ]
    unique_forms = len(cases)
    report = {
        "source_rows": len(source_rows),
        "rows_with_unique_cases": len(output_rows),
        "raw_forms": raw_forms,
        "unique_forms": unique_forms,
        "duplicates_removed": raw_forms - unique_forms,
        "status_counts": dict(status_counts.most_common()),
        "review_counts": dict(review_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "Linguistic cases are deduplicated across the complete report by "
            "(lemma, slot, written form). Source record occurrences are retained on "
            "each surviving case. Every case is then looked up in the complete SALDO "
            "form index."
        ),
    }
    return report, output_rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Källrader: {report['source_rows']}",
        f"Rader med unika fall: {report['rows_with_unique_cases']}",
        f"Saknade former, rått: {report['raw_forms']}",
        f"Unika språkliga fall: {report['unique_forms']}",
        f"Dubbletter borttagna: {report['duplicates_removed']}",
        "",
        "Förekomst i hela SALDO:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    lines.extend(["", "Nästa granskningskategori:"])
    for category, count in report["review_counts"].items():
        lines.append(f"  {count:6d}  {category}")
    for status, examples in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {status}"])
        for item in examples[:20]:
            analyses = ", ".join(
                f"{analysis['id']}:{'/'.join(analysis['lemmas'])}:{analysis['upos']}"
                for analysis in item.get("analyses", ())
            )
            suffix = f" | {analyses}" if analyses else ""
            occurrences = ""
            if item.get("source_occurrence_count", 1) > 1:
                occurrences = f" | förekomster={item['source_occurrence_count']}"
            lines.append(
                f"  {item['lemma']} | {item['slot']}={item['form']} | "
                f"{item['provenance']} | token={item['source_token']} | "
                f"review={item['review_category']}{occurrences}{suffix}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check adjective mismatch forms against every SALDO analysis"
    )
    parser.add_argument("mismatches", nargs="?", type=Path, default=DEFAULT_MISMATCHES)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    saldo = read_saldo(args.saldo)
    form_index = _build_form_index(saldo)
    report, rows = analyze_rows(read_jsonl(args.mismatches), form_index)

    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(args.jsonl, rows)
    print(f"Källrader: {report['source_rows']}")
    print(f"Rader med unika fall: {report['rows_with_unique_cases']}")
    print(f"Saknade former, rått: {report['raw_forms']}")
    print(f"Unika språkliga fall: {report['unique_forms']}")
    print(f"Dubbletter borttagna: {report['duplicates_removed']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
