from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analyze_saldo_forms_beyond_saol_scope import candidates as scope_candidates, read_jsonl

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-article-scope-validation-status.txt")
DEFAULT_JSON = Path("reports/saol14-article-scope-validation-status.json")


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = scope_candidates(rows)
    counts = Counter(str(row.get("status") or "") for row in selected)
    semantic = Counter(str(row.get("semantic_status") or "") for row in selected)
    by_notation: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        status = str(row.get("status") or "")
        notation = str(row.get("notation") or "")
        by_notation[notation][status] += 1
        if len(examples[status]) < 12:
            examples[status].append({
                "lemma": str(row.get("lemma") or ""),
                "notation": notation,
            })
    return {
        "records": len(selected),
        "status_counts": dict(counts.most_common()),
        "semantic_status_counts": dict(semantic.most_common()),
        "notation_status_counts": {
            notation: dict(counter.most_common())
            for notation, counter in sorted(by_notation.items())
        },
        "examples": dict(examples),
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 artikelomfång: valideringsstatus",
        "",
        "Population: NOUN där SAOL-artikeln endast anger +en/+et/+n/+t och SALDO",
        "har ytterligare former som SAOL-generatorn inte genererar.",
        "",
        f"Poster: {summary['records']}",
        "",
        "Status:",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"{count:5}  {status}")
    lines.extend(["", "Semantisk status:"])
    for status, count in summary["semantic_status_counts"].items():
        lines.append(f"{count:5}  {status or '(saknas)'}")
    lines.extend(["", "Per notation:"])
    for notation, counts in summary["notation_status_counts"].items():
        desc = ", ".join(f"{status}={count}" for status, count in counts.items())
        lines.append(f"  {notation}: {desc}")
    lines.extend(["", "Exempel per status:"])
    for status, examples in summary["examples"].items():
        lines.append(f"  {status}:")
        for example in examples:
            lines.append(f"    {example['lemma']} | {example['notation']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
