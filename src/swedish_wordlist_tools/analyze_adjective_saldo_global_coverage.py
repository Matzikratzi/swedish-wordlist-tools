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


def _form_identity(form: dict[str, Any]) -> tuple[str, ...]:
    """Identity for one generated slot form within a SAOL record.

    Duplicate rows can arise when several selected SALDO analyses produce the
    same comparison row. They must not inflate the number of linguistic cases.
    """

    return (
        str(form.get("written_form") or "").casefold(),
        str(form.get("slot") or ""),
        str(form.get("provenance") or ""),
        str(form.get("source_token") or ""),
        str(form.get("operation_base") or "").casefold(),
    )


def _unique_forms(forms: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for form in forms:
        identity = _form_identity(form)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(form)
    return unique


def analyze_rows(
    rows: Iterable[dict[str, Any]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    review_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_forms = 0

    for row in rows:
        source_forms = list(row.get("classified_missing_forms", ()))
        raw_forms += len(source_forms)
        classified_forms = []
        for form in _unique_forms(source_forms):
            written_form = str(form.get("written_form") or "")
            status, analyses = classify_global_presence(written_form, form_index)
            review_category = _review_category(status)
            status_counts[status] += 1
            review_counts[review_category] += 1
            item = {
                **form,
                "global_saldo_status": status,
                "global_review_category": review_category,
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
            classified_forms.append(item)
            if len(examples[status]) < 30:
                examples[status].append({
                    "lemma": row.get("lemma"),
                    "form": written_form,
                    "slot": form.get("slot"),
                    "source_token": form.get("source_token"),
                    "provenance": form.get("provenance"),
                    "review_category": review_category,
                    "analyses": item["global_saldo_analyses"],
                })
        output_rows.append({**row, "classified_missing_forms": classified_forms})

    unique_forms = sum(status_counts.values())
    report = {
        "rows": len(output_rows),
        "raw_forms": raw_forms,
        "unique_forms": unique_forms,
        "duplicates_removed": raw_forms - unique_forms,
        "status_counts": dict(status_counts.most_common()),
        "review_counts": dict(review_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "Duplicate generated slot forms within one SAOL record are collapsed before "
            "counting. Each unique form already missing from the selected SALDO analysis "
            "is then looked up in the complete SALDO form index."
        ),
    }
    return report, output_rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Rader: {report['rows']}",
        f"Saknade former, rått: {report['raw_forms']}",
        f"Unika saknade former: {report['unique_forms']}",
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
            lines.append(
                f"  {item['lemma']} | {item['slot']}={item['form']} | "
                f"{item['provenance']} | token={item['source_token']} | "
                f"review={item['review_category']}{suffix}"
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
    print(f"Rader: {report['rows']}")
    print(f"Saknade former, rått: {report['raw_forms']}")
    print(f"Unika saknade former: {report['unique_forms']}")
    print(f"Dubbletter borttagna: {report['duplicates_removed']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
