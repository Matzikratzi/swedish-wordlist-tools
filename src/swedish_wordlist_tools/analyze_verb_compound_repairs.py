from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_compound_heads import borrow_compound_verb_slots, build_simple_verb_paradigm_index
from .verb_game_fallback import interpret_playable_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-compound-repairs.txt")
DEFAULT_JSON = Path("reports/saol14-verb-compound-repairs.json")


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record
        for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "VERB"
    ]
    direct = {
        id(record): interpret_playable_verb_slots(record)
        for record in records
    }
    head_index = build_simple_verb_paradigm_index(records, direct)

    repaired_rows: list[dict[str, Any]] = []
    direct_count = 0
    exported_count = 0
    for record in records:
        before = direct[id(record)]
        if before is not None:
            direct_count += 1
        after = borrow_compound_verb_slots(record, head_index, before)
        if after is None:
            continue
        exported_count += 1
        if before is None:
            repaired_rows.append(
                {
                    "lemma": str(record.get("normaliserat_ord") or ""),
                    "homonym_number": str(record.get("homonr") or ""),
                    "text": str(record.get("text") or ""),
                    "stycke": str(record.get("stycke") or ""),
                    "forms": list(after.written_forms()),
                }
            )

    return {
        "verb_records": len(records),
        "directly_interpreted_records": direct_count,
        "compound_repaired_records": len(repaired_rows),
        "exported_interpreted_records": exported_count,
        "arithmetic_matches": direct_count + len(repaired_rows) == exported_count,
        "records": repaired_rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Direkt tolkade poster: {report['directly_interpreted_records']}",
        f"Sammansättningsreparerade poster: {report['compound_repaired_records']}",
        f"Exporterade tolkade poster: {report['exported_interpreted_records']}",
        f"Summan stämmer: {'ja' if report['arithmetic_matches'] else 'nej'}",
        "",
        "Sammansättningsreparerade poster:",
    ]
    if not report["records"]:
        lines.append("  (inga)")
    for row in report["records"]:
        lines.append(
            f"  {row['lemma']} (homonr={row['homonym_number'] or '-'}) | "
            f"text={row['text']!r} | former={', '.join(row['forms'])}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit verb records repaired from compound heads")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Direkt tolkade poster: {report['directly_interpreted_records']}")
    print(f"Sammansättningsreparerade poster: {report['compound_repaired_records']}")
    print(f"Exporterade tolkade poster: {report['exported_interpreted_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
