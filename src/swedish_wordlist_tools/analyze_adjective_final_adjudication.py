from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_GLOBAL = Path("reports/saol14-adjective-saldo-global-coverage.jsonl")
DEFAULT_ABSENT = Path("reports/saol14-adjective-saldo-absent-review.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-final-adjudication.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-final-adjudication.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-final-adjudication.jsonl")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _key(values: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(values.get("lemma") or "").casefold(),
        str(values.get("slot") or ""),
        str(values.get("written_form") or "").casefold(),
    )


def read_confirmed_absent(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    return {
        _key(row)
        for row in read_jsonl(path)
        if row.get("review_assessment") == "strong_saldo_gap_candidate"
    }


def adjudicate(status: str, confirmed_absent: bool) -> str:
    if status == "absent_from_all_saldo" and confirmed_absent:
        return "confirmed_saldo_gap"
    if status == "absent_from_all_saldo":
        return "unconfirmed_saldo_or_saol_review"
    if status == "found_in_other_saldo_adjective_analysis":
        return "saldo_adjective_alignment"
    if status == "only_non_adjective_saldo_match":
        return "saldo_pos_or_adjective_coverage_review"
    return "unresolved"


def build_report(
    rows: Iterable[dict[str, Any]],
    confirmed_absent: set[tuple[str, str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        lemma = str(row.get("lemma") or "")
        for form in row.get("classified_missing_forms", ()):
            identity = _key({**form, "lemma": lemma})
            status = str(form.get("global_saldo_status") or "")
            final_status = adjudicate(status, identity in confirmed_absent)
            cases.append({
                "lemma": lemma,
                "homonym_number": str(row.get("homonym_number") or ""),
                "slot": str(form.get("slot") or ""),
                "written_form": str(form.get("written_form") or ""),
                "provenance": str(form.get("provenance") or ""),
                "source_token": str(form.get("source_token") or ""),
                "operation_base": str(form.get("operation_base") or ""),
                "global_saldo_status": status,
                "final_adjudication": final_status,
                "source_occurrence_count": int(form.get("source_occurrence_count") or 1),
                "global_saldo_analyses": list(form.get("global_saldo_analyses") or ()),
            })

    cases.sort(key=lambda item: (
        item["final_adjudication"],
        item["lemma"].casefold(),
        item["slot"],
        item["written_form"].casefold(),
    ))
    counts = Counter(case["final_adjudication"] for case in cases)
    slot_counts = Counter(case["slot"] for case in cases)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if len(examples[case["final_adjudication"]]) < 30:
            examples[case["final_adjudication"]].append(case)

    report = {
        "cases": len(cases),
        "adjudication_counts": dict(counts.most_common()),
        "slot_counts": dict(slot_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "All cases are unique by lemma, slot and written form. Forms absent from "
            "all SALDO analyses are called confirmed SALDO gaps only when the separate "
            "SAOL-notation review has confirmed their generation. Forms found under "
            "another adjective analysis are alignment cases; forms found only outside "
            "ADJ remain POS or adjective-coverage review cases."
        ),
    }
    return report, cases


def render_text(report: dict[str, Any]) -> str:
    lines = [f"Unika adjektivavvikelser: {report['cases']}", "", "Slutlig bedömning:"]
    for status, count in report["adjudication_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    lines.extend(["", "Per slot:"])
    for slot, count in report["slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")
    for status, examples in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {status}"])
        for item in examples:
            analyses = ", ".join(
                f"{analysis.get('id', '')}:{'/'.join(analysis.get('lemmas', ())) or '-'}:{analysis.get('upos', '')}"
                for analysis in item.get("global_saldo_analyses", ())
            )
            suffix = f" | SALDO={analyses}" if analyses else ""
            occurrences = (
                f" | förekomster={item['source_occurrence_count']}"
                if item["source_occurrence_count"] > 1 else ""
            )
            lines.append(
                f"  {item['lemma']} | {item['slot']}={item['written_form']} | "
                f"{item['provenance']} | token={item['source_token']}"
                f"{occurrences}{suffix}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create final adjective mismatch adjudication")
    parser.add_argument("global_coverage", nargs="?", type=Path, default=DEFAULT_GLOBAL)
    parser.add_argument("--absent-review", type=Path, default=DEFAULT_ABSENT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    confirmed = read_confirmed_absent(args.absent_review)
    report, cases = build_report(read_jsonl(args.global_coverage), confirmed)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(args.jsonl, cases)
    print(f"Unika adjektivavvikelser: {report['cases']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
