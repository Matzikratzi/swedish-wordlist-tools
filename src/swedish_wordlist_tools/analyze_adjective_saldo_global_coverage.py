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


def analyze_rows(
    rows: Iterable[dict[str, Any]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        classified_forms = []
        for form in row.get("classified_missing_forms", ()):
            written_form = str(form.get("written_form") or "")
            status, analyses = classify_global_presence(written_form, form_index)
            status_counts[status] += 1
            item = {
                **form,
                "global_saldo_status": status,
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
                    "analyses": item["global_saldo_analyses"],
                })
        output_rows.append({**row, "classified_missing_forms": classified_forms})

    report = {
        "rows": len(output_rows),
        "forms": sum(status_counts.values()),
        "status_counts": dict(status_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "Each form already missing from the selected SALDO analysis is looked up in "
            "the complete SALDO form index. This distinguishes an alignment/selection "
            "problem from a form absent from SALDO altogether."
        ),
    }
    return report, output_rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Rader: {report['rows']}",
        f"Saknade former: {report['forms']}",
        "",
        "Förekomst i hela SALDO:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")
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
                f"{item['provenance']} | token={item['source_token']}{suffix}"
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
    print(f"Saknade former: {report['forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
