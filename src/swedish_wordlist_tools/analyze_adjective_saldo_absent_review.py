from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-adjective-saldo-global-coverage.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-saldo-absent-review.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-saldo-absent-review.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-saldo-absent-review.jsonl")

REGULAR_APPEND_TOKENS = {"+a", "+t", "+e", "+ma"}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def review_priority(form: dict[str, Any]) -> tuple[int, str]:
    provenance = str(form.get("provenance") or "")
    token = str(form.get("source_token") or "")
    if provenance == "explicit":
        return 0, "explicit_saol_form"
    if provenance == "replace_tail":
        return 1, "replace_tail_form"
    if provenance == "append" and token not in REGULAR_APPEND_TOKENS:
        return 2, "uncommon_append_form"
    if provenance == "append":
        return 3, "regular_append_form"
    return 4, "other"


def review_assessment(form: dict[str, Any]) -> str:
    """Choose the next evidence-based action for a SALDO-absent form."""

    provenance = str(form.get("provenance") or "")
    token = str(form.get("source_token") or "")
    if provenance == "explicit":
        return "strong_saldo_gap_candidate"
    if provenance == "append" and token in REGULAR_APPEND_TOKENS:
        return "standard_notation_saldo_gap_candidate"
    if provenance == "replace_tail":
        return "targeted_saol_notation_review"
    return "manual_notation_review"


def build_report(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        for form in row.get("classified_missing_forms", ()):
            if form.get("global_saldo_status") != "absent_from_all_saldo":
                continue
            rank, group = review_priority(form)
            assessment = review_assessment(form)
            cases.append({
                "lemma": str(row.get("lemma") or ""),
                "homonym_number": str(row.get("homonym_number") or ""),
                "slot": str(form.get("slot") or ""),
                "written_form": str(form.get("written_form") or ""),
                "provenance": str(form.get("provenance") or ""),
                "source_token": str(form.get("source_token") or ""),
                "operation_base": str(form.get("operation_base") or ""),
                "source_occurrence_count": int(form.get("source_occurrence_count") or 1),
                "review_group": group,
                "review_assessment": assessment,
                "priority": rank,
                "notation": str(row.get("effective_notation") or row.get("notation") or ""),
                "stycke": str(row.get("stycke") or ""),
            })

    cases.sort(key=lambda item: (
        item["priority"],
        item["source_token"].casefold(),
        item["lemma"].casefold(),
        item["slot"],
        item["written_form"].casefold(),
    ))

    group_counts = Counter(case["review_group"] for case in cases)
    assessment_counts = Counter(case["review_assessment"] for case in cases)
    slot_counts = Counter(case["slot"] for case in cases)
    provenance_counts = Counter(case["provenance"] for case in cases)
    token_counts = Counter(case["source_token"] for case in cases if case["source_token"])
    grouped_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if len(grouped_examples[case["review_group"]]) < 30:
            grouped_examples[case["review_group"]].append(case)

    report = {
        "cases": len(cases),
        "review_group_counts": dict(group_counts.most_common()),
        "review_assessment_counts": dict(assessment_counts.most_common()),
        "slot_counts": dict(slot_counts.most_common()),
        "provenance_counts": dict(provenance_counts.most_common()),
        "source_token_counts": dict(token_counts.most_common()),
        "examples": dict(grouped_examples),
        "note": (
            "Only unique adjective forms absent from every SALDO analysis are included. "
            "Explicit forms are strong SALDO-gap candidates. Standard append operations "
            "are separated from tail replacements that still merit targeted notation review."
        ),
    }
    return report, cases


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Former som saknas helt i SALDO: {report['cases']}",
        "",
        "Bedömd nästa åtgärd:",
    ]
    for assessment, count in report["review_assessment_counts"].items():
        lines.append(f"  {count:6d}  {assessment}")
    lines.extend(["", "Prioriterad granskningsgrupp:"])
    for group, count in report["review_group_counts"].items():
        lines.append(f"  {count:6d}  {group}")
    lines.extend(["", "Per slot:"])
    for slot, count in report["slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")
    lines.extend(["", "Per härledning:"])
    for provenance, count in report["provenance_counts"].items():
        lines.append(f"  {count:6d}  {provenance}")
    lines.extend(["", "Vanligaste SAOL-token:"])
    for token, count in list(report["source_token_counts"].items())[:30]:
        lines.append(f"  {count:6d}  {token}")

    for group, examples in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {group}"])
        for item in examples:
            occurrences = (
                f" | förekomster={item['source_occurrence_count']}"
                if item["source_occurrence_count"] > 1 else ""
            )
            lines.append(
                f"  {item['lemma']} | {item['slot']}={item['written_form']} | "
                f"{item['provenance']} | token={item['source_token']} | "
                f"base={item['operation_base']} | assessment={item['review_assessment']}"
                f"{occurrences}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prioritize adjective forms absent from every SALDO analysis"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    report, cases = build_report(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(args.jsonl, cases)
    print(f"Former som saknas helt i SALDO: {report['cases']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
