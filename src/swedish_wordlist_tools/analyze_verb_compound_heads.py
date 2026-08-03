from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_compound_heads import (
    borrow_compound_verb_slots,
    build_simple_verb_paradigm_index,
    compound_verb_parts,
)
from .verb_slots import interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-compound-heads.txt")
DEFAULT_JSON = Path("reports/saol14-verb-compound-heads.json")


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record
        for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "VERB"
    ]
    interpreted = {id(record): interpret_verb_slots(record) for record in records}
    index = build_simple_verb_paradigm_index(records, interpreted)

    bar_marked = 0
    exact_head_found = 0
    recovered_rows = 0
    enriched_rows = 0
    borrowed_slot_counts: dict[str, int] = {}
    examples: list[dict[str, Any]] = []

    for record in records:
        parts = compound_verb_parts(record)
        if parts is None:
            continue
        bar_marked += 1
        _prefix, head, _trailing = parts
        if head not in index:
            continue
        exact_head_found += 1
        current = interpreted[id(record)]
        enriched = borrow_compound_verb_slots(record, index, current)
        if enriched is None or enriched is current:
            continue

        before_slots = set(current.slots()) if current is not None else set()
        added_slots = [slot for slot in enriched.slots() if slot not in before_slots]
        for slot in added_slots:
            borrowed_slot_counts[slot] = borrowed_slot_counts.get(slot, 0) + 1
        if current is None:
            recovered_rows += 1
        else:
            enriched_rows += 1
        if len(examples) < 40:
            examples.append({
                "lemma": enriched.lemma,
                "head": head,
                "stycke": str(record.get("stycke") or ""),
                "added_slots": added_slots,
                "forms": {
                    slot: list(enriched.forms_for(slot))
                    for slot in added_slots
                },
            })

    return {
        "verb_records": len(records),
        "bar_marked_compound_verbs": bar_marked,
        "exact_independent_head_found": exact_head_found,
        "fully_recovered_rows": recovered_rows,
        "partly_enriched_rows": enriched_rows,
        "borrowed_slot_counts": dict(sorted(borrowed_slot_counts.items())),
        "independent_head_index_size": len(index),
        "examples": examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Lodstrecksmarkerade sammansatta verb: {report['bar_marked_compound_verbs']}",
        f"Exakt självständigt huvudverb hittat: {report['exact_independent_head_found']}",
        f"Helt räddade rader: {report['fully_recovered_rows']}",
        f"Redan tolkade rader med nya slots: {report['partly_enriched_rows']}",
        f"Självständiga huvudverb i index: {report['independent_head_index_size']}",
        "",
        "Lånade slots:",
    ]
    for slot, count in report["borrowed_slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")
    lines.extend(["", "Exempel:"])
    for example in report["examples"]:
        lines.append(
            f"  {example['lemma']} <- {example['head']} | "
            f"slots={','.join(example['added_slots'])} | {example['forms']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse exact compound verb head recovery")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(render_text(report), end="")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
