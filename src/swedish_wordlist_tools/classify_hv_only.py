from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .audit_ignore_hv import analyze as audit_ignore_hv
from .jsonl import read_jsonl

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-hv-only-classification.txt")
DEFAULT_JSON = Path("reports/saol14-hv-only-classification.json")

UNKNOWN_WORD = "UNKNOWN_WORD"
CONTEXT_ONLY = "CONTEXT_ONLY"


def _words(value: str) -> list[str]:
    return [part for part in re.split(r"[^0-9A-Za-zÅÄÖåäöÉéÜü]+", value.casefold()) if part]


def classify_case(case: dict[str, Any]) -> tuple[str, str]:
    """Classify one form that survives only through an (hv) row.

    We deliberately do not infer a word class.  A form is CONTEXT_ONLY only
    when the export itself gives strong structural evidence that it belongs to
    a multiword expression: either the printed form is multiword, or it is a
    strict token/subphrase of the multiword normalized expression.  Everything
    else is retained as an UNKNOWN_WORD and is not inflected further.
    """

    form = str(case.get("form") or "").strip()
    lemma = str(case.get("hv_lemma") or "").strip()
    if not form:
        return CONTEXT_ONLY, "empty_form"

    if re.search(r"\s", form):
        return CONTEXT_ONLY, "printed_form_is_multiword"

    lemma_words = _words(lemma)
    form_words = _words(form)
    if len(lemma_words) > 1 and form_words:
        # The common SAOL cases are hux flux -> flux, till spillo -> spillo,
        # status quo -> quo, etc.  Require the form to occur as a strict token
        # sequence inside the multiword expression; do not use semantics.
        n = len(form_words)
        for start in range(len(lemma_words) - n + 1):
            if lemma_words[start : start + n] == form_words:
                return CONTEXT_ONLY, "strict_part_of_multiword_lemma"

    return UNKNOWN_WORD, "standalone_hv_only_form"


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    audit = audit_ignore_hv(records)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()

    for case in audit["cases"]:
        if case.get("status") != "hv_only":
            continue
        classification, reason = classify_case(case)
        key = (str(case.get("form") or "").casefold(), classification)
        if key in seen:
            continue
        seen.add(key)
        counts[classification] += 1
        reason_counts[reason] += 1
        rows.append({
            "form": case.get("form"),
            "classification": classification,
            "reason": reason,
            "upos": "X" if classification == UNKNOWN_WORD else None,
            "generate_inflections": False,
            "hv_lemma": case.get("hv_lemma"),
            "hv_homonr": case.get("hv_homonr"),
            "hv_record_id": case.get("hv_record_id"),
        })

    rows.sort(key=lambda row: (row["classification"], str(row["form"]).casefold()))
    return {
        "hv_only_unique_forms": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: klassificering av former som bara återstår via (hv)",
        "",
        "UNKNOWN_WORD = SAOL belägger själva formen men exporten räcker inte för",
        "att fastställa ordklass/sammanhang. Formen tas med som den står, UPOS=X,",
        "och inga ytterligare böjningar genereras.",
        "CONTEXT_ONLY = stark strukturell signal att formen är hela eller del av",
        "ett flerordsuttryck; den tas inte med som fristående ord.",
        "",
        f"Unika hv_only-former: {report['hv_only_unique_forms']}",
        "Klassificering:",
    ]
    for key, count in report["classification_counts"].items():
        lines.append(f"  {count:4d}  {key}")
    lines.append("Orsaker:")
    for key, count in report["reason_counts"].items():
        lines.append(f"  {count:4d}  {key}")

    for classification in (UNKNOWN_WORD, CONTEXT_ONLY):
        matching = [row for row in report["rows"] if row["classification"] == classification]
        lines.extend(["", "=" * 78, f"{classification}: {len(matching)}"])
        for row in matching:
            lines.append(
                f"  {row['form']!r} <- hv {row['hv_lemma']}({row['hv_homonr']}) | {row['reason']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify SAOL forms that survive only through (hv) rows")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"hv_only-former: {report['hv_only_unique_forms']}")
    for key, count in report["classification_counts"].items():
        print(f"{key}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
