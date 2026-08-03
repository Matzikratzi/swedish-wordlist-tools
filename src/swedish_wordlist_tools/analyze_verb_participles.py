from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_participles import add_explicit_perfect_participles
from .verb_slots import interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-participles.txt")
DEFAULT_JSON = Path("reports/saol14-verb-participles.json")
_PARTICIPLE_SLOTS = (
    "perfect_participle_common",
    "perfect_participle_neuter",
    "perfect_participle_plural",
)


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    verb_records = 0
    interpreted_records = 0
    rows_with_participles = 0
    slot_counts = {slot: 0 for slot in _PARTICIPLE_SLOTS}
    unique_forms: set[str] = set()
    examples: list[dict[str, Any]] = []

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        verb_records += 1
        base = interpret_verb_slots(record)
        if base is None:
            continue
        interpreted_records += 1
        enriched = add_explicit_perfect_participles(record, base)
        forms_by_slot = {
            slot: enriched.forms_for(slot)
            for slot in _PARTICIPLE_SLOTS
        }
        if not any(forms_by_slot.values()):
            continue
        rows_with_participles += 1
        for slot, forms in forms_by_slot.items():
            if forms:
                slot_counts[slot] += 1
                unique_forms.update(forms)
        if len(examples) < 30:
            examples.append({
                "lemma": enriched.lemma,
                "text": str(record.get("text") or ""),
                "forms": {slot: list(forms) for slot, forms in forms_by_slot.items()},
            })

    return {
        "verb_records": verb_records,
        "interpreted_records": interpreted_records,
        "rows_with_explicit_perfect_participles": rows_with_participles,
        "slot_counts": slot_counts,
        "unique_participle_forms": len(unique_forms),
        "examples": examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Radtolkade verbposter: {report['interpreted_records']}",
        "Verb med explicit perfektparticiptrio: "
        f"{report['rows_with_explicit_perfect_participles']}",
        f"Nya unika participformer: {report['unique_participle_forms']}",
        "",
        "Slots:",
    ]
    for slot, count in report["slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")
    lines.extend(["", "Exempel:"])
    for example in report["examples"]:
        lines.append(f"  {example['lemma']} | {example['forms']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse explicit perfect participles in SAOL verb rows"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
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
