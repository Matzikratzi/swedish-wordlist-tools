from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_game_fallback import interpret_playable_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-legacy-fallback.txt")
DEFAULT_JSON = Path("reports/saol14-verb-legacy-fallback.json")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        slots = interpret_playable_verb_slots(record)
        if slots is None:
            continue
        fallback_kind = slots.metadata.get("fallback_kind")
        if not fallback_kind:
            continue
        kind_counts[fallback_kind] += 1
        rows.append(
            {
                "lemma": _value(record, "normaliserat_ord"),
                "homonym_number": _value(record, "homonr"),
                "text": _value(record, "text") or None,
                "stycke": _value(record, "stycke"),
                "fallback_kind": fallback_kind,
                "forms": list(slots.written_forms()),
                "slots": list(slots.slots()),
            }
        )

    rows.sort(key=lambda row: (row["fallback_kind"], row["lemma"], row["homonym_number"]))
    return {
        "legacy_fallback_records": len(rows),
        "fallback_kind_counts": dict(kind_counts.most_common()),
        "records": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Äldre fallbackposter: {report['legacy_fallback_records']}",
        "",
        "Fallbacktyper:",
    ]
    if not report["fallback_kind_counts"]:
        lines.append("  (inga)")
    for kind, count in report["fallback_kind_counts"].items():
        lines.append(f"  {count:6d}  {kind}")
    lines.extend(["", "Poster:"])
    if not report["records"]:
        lines.append("  (inga)")
    for row in report["records"]:
        lines.append(
            f"  {row['lemma']} (homonr={row['homonym_number'] or '-'}) | "
            f"kind={row['fallback_kind']} | text={row['text']!r} | "
            f"forms={row['forms']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="List verb records handled by the legacy game fallback")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Äldre fallbackposter: {report['legacy_fallback_records']}")
    for kind, count in report["fallback_kind_counts"].items():
        print(f"{kind}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
