from __future__ import annotations

import argparse
import json
from pathlib import Path

from .jsonl import read_jsonl
from .pronoun_shared_interpreter import interpret_pronoun_row
from .saol_source_policy import is_truncated_inflection_source, raw_inflection_text

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-pronoun-shared-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-pronoun-shared-coverage.json")


def analyze(records):
    rows = []
    total = text_records = interpreted = truncated = 0
    for record in records:
        if str(record.get("upos") or "").upper() != "PRON":
            continue
        total += 1
        text = raw_inflection_text(record)
        if not text:
            continue
        text_records += 1
        is_truncated = is_truncated_inflection_source(record)
        truncated += int(is_truncated)
        slots = interpret_pronoun_row(record)
        if slots is not None:
            interpreted += 1
        rows.append({
            "lemma": str(record.get("normaliserat_ord") or ""),
            "homonr": str(record.get("homonr") or ""),
            "text": text,
            "truncated": is_truncated,
            "status": "shared" if slots is not None else "remaining_structure",
            "forms": list(slots.written_forms()) if slots is not None else [],
            "slots": list(slots.slots()) if slots is not None else [],
        })
    return {
        "pronoun_records": total,
        "text_records": text_records,
        "truncated_records": truncated,
        "shared_records": interpreted,
        "remaining_records": text_records - interpreted,
        "coverage_percent": round(100 * interpreted / text_records, 2) if text_records else 0.0,
        "rows": rows,
    }


def render_text(report):
    lines = [
        "SAOL14 PRON: första shared-täckningen",
        "",
        "Konservativt första pass: explicita former, +operationer, kända etiketter",
        "och alternativ tolkas. '-' lämnas tills lodstrecksbasen är verifierad.",
        "",
        f"PRON-poster: {report['pronoun_records']}",
        f"Med textfält: {report['text_records']}",
        f"Trunkerade: {report['truncated_records']}",
        f"Shared tolkade: {report['shared_records']} ({report['coverage_percent']:.2f} %)",
        f"Kvarvarande struktur: {report['remaining_records']}",
        "",
        "remaining_structure:",
    ]
    remaining = [row for row in report["rows"] if row["status"] != "shared"]
    if not remaining:
        lines.append("  (inga)")
    else:
        for row in remaining:
            marker = " | TRUNKERAD" if row["truncated"] else ""
            lines.append(
                f"  {row['lemma']} ({row['homonr']}){marker} | text='{row['text']}'"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure first shared PRON coverage")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PRON-poster: {report['pronoun_records']}")
    print(f"Med textfält: {report['text_records']}")
    print(f"Shared tolkade: {report['shared_records']} ({report['coverage_percent']:.2f} %)")
    print(f"Kvarvarande struktur: {report['remaining_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
