from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .replay_adjective_form import replay_generated_form
from .saol_boundaries import bar_prefix
from .saol_notation import parse_form_operation

DEFAULT_INPUT = Path("reports/saol14-adjective-saldo-absent-review.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-replace-tail-review.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-replace-tail-review.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-replace-tail-review.jsonl")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    lemma = str(case.get("lemma") or "")
    stycke = str(case.get("stycke") or "")
    token = str(case.get("source_token") or "")
    operation = parse_form_operation(token)
    replacement = operation.value if operation is not None else ""
    prefix = bar_prefix(stycke, lemma)
    reconstructed = prefix + replacement if prefix and replacement else ""
    replay = replay_generated_form(
        lemma=lemma,
        stycke=stycke,
        written_form=str(case.get("written_form") or ""),
        slot=str(case.get("slot") or ""),
        provenance=str(case.get("provenance") or ""),
        source_token=token,
        notation=str(case.get("notation") or ""),
        operation_base=str(case.get("operation_base") or ""),
    )
    if prefix and reconstructed == str(case.get("written_form") or "").casefold():
        assessment = "bar_notation_confirms_form"
    elif replay.status == "match":
        assessment = "fallback_confirms_form"
    else:
        assessment = "needs_manual_notation_review"
    return {
        **case,
        "bar_prefix": prefix,
        "replacement_tail": replacement,
        "bar_reconstructed_form": reconstructed,
        "replay_status": replay.status,
        "replayed_form": replay.replayed_form,
        "replace_tail_assessment": assessment,
    }


def build_report(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = [
        analyze_case(row)
        for row in rows
        if row.get("review_group") == "replace_tail_form"
    ]
    counts = Counter(case["replace_tail_assessment"] for case in cases)
    return {
        "cases": len(cases),
        "assessment_counts": dict(counts.most_common()),
        "note": (
            "Each tail-replacement case is checked directly against stycke. "
            "When a lodstreck prefix exists, prefix + replacement tail must equal "
            "the canonical generated form."
        ),
    }, cases


def render_text(report: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [f"Replace-tail-fall: {report['cases']}", "", "Bedömning:"]
    for status, count in report["assessment_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    lines.extend(["", "Fall:"])
    for case in cases:
        lines.append(
            f"  {case['lemma']} | stycke={case['stycke']} | token={case['source_token']} | "
            f"prefix={case['bar_prefix']} | tail={case['replacement_tail']} | "
            f"rekonstruerad={case['bar_reconstructed_form']} | "
            f"form={case['written_form']} | {case['replace_tail_assessment']}"
        )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review adjective replace-tail forms against SAOL lodstreck"
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
    print(f"Replace-tail-fall: {report['cases']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
