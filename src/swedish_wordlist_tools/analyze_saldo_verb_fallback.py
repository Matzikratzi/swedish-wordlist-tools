from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .compare_sources import read_saldo
from .jsonl import read_jsonl
from .saldo_verb_fallback import add_saldo_attested_forms
from .verb_slot_schema import add_explicit_verb_row_slots
from .verb_slots import interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-saldo-verb-fallback.txt")
DEFAULT_JSON = Path("reports/saol14-saldo-verb-fallback.json")


def build_report(saol_path: Path = DEFAULT_SAOL, saldo_path: Path = DEFAULT_SALDO) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    verb_records = 0
    matched_records = 0
    enriched_records = 0
    new_forms: set[str] = set()
    provenance_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        verb_records += 1
        slots = interpret_verb_slots(record)
        if slots is None:
            continue
        slots = add_explicit_verb_row_slots(record, slots)
        analyses = saldo.get(slots.lemma.casefold(), ())
        if analyses:
            matched_records += 1
        enriched = add_saldo_attested_forms(slots, analyses)
        added = enriched.forms_for("saldo_attested")
        if added:
            enriched_records += 1
            new_forms.update(added)
            if len(examples) < 40:
                examples.append({"lemma": slots.lemma, "forms": list(added)})
        provenance_counts.update(enriched.provenance_counts())

    return {
        "verb_records": verb_records,
        "exact_saldo_matches": matched_records,
        "records_with_new_saldo_forms": enriched_records,
        "new_unique_saldo_forms": len(new_forms),
        "provenance_counts": dict(provenance_counts.most_common()),
        "examples": examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Exakta lemmaträffar i SALDO: {report['exact_saldo_matches']}",
        f"Poster med nya SALDO-former: {report['records_with_new_saldo_forms']}",
        f"Nya unika SALDO-former: {report['new_unique_saldo_forms']}",
        "",
        "Former efter ursprung:",
    ]
    for source, count in report["provenance_counts"].items():
        lines.append(f"  {count:7d}  {source}")
    lines.extend(["", "Exempel på tillagda SALDO-former:"])
    for example in report["examples"]:
        lines.append(f"  {example['lemma']} | {', '.join(example['forms'])}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure exact-lemma SALDO verb forms added for the game word list")
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
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(text, end="")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
