from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-adjective-saldo-absent-review.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-append-review.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-append-review.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-append-review.jsonl")

LITERAL_APPEND_TOKENS = {"+a", "+t", "+e", "+ma"}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    base = str(case.get("operation_base") or "").casefold()
    token = str(case.get("source_token") or "").casefold()
    form = str(case.get("written_form") or "").casefold()
    suffix = token[1:] if token.startswith("+") else ""
    literal_form = base + suffix if suffix else ""

    if token in LITERAL_APPEND_TOKENS and literal_form == form:
        assessment = "literal_append_confirms_form"
    else:
        assessment = "needs_manual_append_review"

    return {
        **case,
        "literal_appended_form": literal_form,
        "append_assessment": assessment,
    }


def build_report(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = [
        analyze_case(row)
        for row in rows
        if row.get("review_group") == "regular_append_form"
    ]
    counts = Counter(case["append_assessment"] for case in cases)
    return {
        "cases": len(cases),
        "assessment_counts": dict(counts.most_common()),
        "note": (
            "SAOL +a, +t, +e and +ma operations are checked literally as base + suffix. "
            "Irregular adjective spellings are written out explicitly in SAOL rather than "
            "being encoded by a + operation."
        ),
    }, cases


def render_text(report: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [f"Append-fall: {report['cases']}", "", "Bedömning:"]
    for status, count in report["assessment_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    lines.extend(["", "Fall:"])
    for case in cases:
        lines.append(
            f"  {case['lemma']} | {case['slot']}={case['written_form']} | "
            f"token={case['source_token']} | base={case['operation_base']} | "
            f"literal={case['literal_appended_form']} | {case['append_assessment']}"
        )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review regular adjective append forms absent from SALDO"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    report, cases = build_report(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report, cases), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(args.jsonl, cases)
    print(f"Append-fall: {report['cases']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
