from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .compare_sources import _build_form_index, read_saldo
from .jsonl import read_jsonl
from .validate_direct_forms import select_direct_match
from .verb_participles import add_explicit_perfect_participles
from .verb_slots import interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-verb-participles-saldo.txt")
DEFAULT_JSON = Path("reports/saol14-verb-participles-saldo.json")

_PARTICIPLE_SLOTS = (
    "perfect_participle_common",
    "perfect_participle_neuter",
    "perfect_participle_plural",
)


def _casefolded(values: set[str]) -> set[str]:
    return {value.casefold() for value in values}


def build_report(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    verb_records = 0
    rows_with_participles = 0
    direct_matches = 0
    status_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        verb_records += 1
        base = interpret_verb_slots(record)
        if base is None:
            continue
        enriched = add_explicit_perfect_participles(record, base)
        participles = {
            form
            for slot in _PARTICIPLE_SLOTS
            for form in enriched.forms_for(slot)
        }
        if not participles:
            continue
        rows_with_participles += 1

        selected = select_direct_match(record, saldo, form_index)
        if selected is None:
            status_counts["no_direct_saldo_match"] += 1
            continue
        direct_matches += 1
        _match_method, analyses = selected
        saldo_forms = {
            str(form)
            for analysis in analyses
            for form in analysis.get("forms", ())
            if str(form) and not str(form).rstrip().endswith("-")
        }
        missing_folded = _casefolded(participles) - _casefolded(saldo_forms)
        missing = sorted(
            {form for form in participles if form.casefold() in missing_folded},
            key=str.casefold,
        )
        status = (
            "all_participles_in_saldo"
            if not missing
            else "some_participles_missing_from_saldo"
        )
        status_counts[status] += 1
        if missing and len(examples) < 50:
            examples.append(
                {
                    "lemma": enriched.lemma,
                    "notation": enriched.notation,
                    "participles": sorted(participles, key=str.casefold),
                    "missing_from_saldo": missing,
                }
            )

    validated = status_counts.get("all_participles_in_saldo", 0) + status_counts.get(
        "some_participles_missing_from_saldo", 0
    )
    return {
        "verb_records": verb_records,
        "rows_with_explicit_participles": rows_with_participles,
        "direct_saldo_matches": direct_matches,
        "validated_rows": validated,
        "status_counts": dict(status_counts.most_common()),
        "all_participles_in_saldo_percent": round(
            100 * status_counts.get("all_participles_in_saldo", 0) / validated, 2
        ) if validated else 0.0,
        "examples": examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Rader med explicit perfektparticiptrio: {report['rows_with_explicit_participles']}",
        f"Direktmatchade mot SALDO: {report['direct_saldo_matches']}",
        f"Alla participformer finns i SALDO: {report['all_participles_in_saldo_percent']:.2f} %",
        "",
        "Status:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    if report["examples"]:
        lines.extend(["", "Exempel: participformer som saknas i SALDO"])
        for row in report["examples"][:30]:
            lines.append(
                f"  {row['lemma']} | {row['notation']} | saknas: "
                + ", ".join(row["missing_from_saldo"])
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate explicit SAOL verb participles directly against SALDO"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol, args.saldo)
    text = render_text(report)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(text, encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(text, end="")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
