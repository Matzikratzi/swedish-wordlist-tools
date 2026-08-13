from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .classify_hv_only import analyze as classify_hv_only
from .jsonl import read_jsonl

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-ofta-family.txt")
DEFAULT_JSON = Path("reports/saol14-ofta-family.json")

_TARGETS = ("ofta", "oftare", "oftast")
_FIELDS = ("ord", "normaliserat_ord", "stycke", "text")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None:
        return ""
    return str(value)


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    matching: list[dict[str, Any]] = []
    for record in records:
        haystack = "\n".join(_value(record, field).casefold() for field in _FIELDS)
        if not any(target in haystack for target in _TARGETS):
            continue
        matching.append({
            "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
            "ord": record.get("ord"),
            "normaliserat_ord": record.get("normaliserat_ord"),
            "homonr": record.get("homonr"),
            "ordkl": record.get("ordkl"),
            "text": record.get("text"),
            "upos": record.get("upos"),
        })

    hv_report = classify_hv_only(records)
    hv_rows = [
        row for row in hv_report["rows"]
        if str(row.get("form") or "").casefold() in _TARGETS
    ]
    return {
        "matching_records": matching,
        "hv_only_rows": hv_rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = ["SAOL14: ofta/oftare/oftast audit", "", "Källrader:"]
    for row in report["matching_records"]:
        lines.append(
            f"  id={row['record_id']} ord={row['ord']!r} norm={row['normaliserat_ord']!r} "
            f"hom={row['homonr']} upos={row['upos']} ordkl={row['ordkl']!r} text={row['text']!r}"
        )
    lines.extend(["", "hv_only:"])
    if not report["hv_only_rows"]:
        lines.append("  (inga)")
    else:
        for row in report["hv_only_rows"]:
            lines.append(
                f"  form={row.get('form')!r} class={row.get('classification')} "
                f"norm={row.get('normaliserat_ord')!r} hv_id={row.get('hv_record_id')!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SAOL rows for ofta/oftare/oftast")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(list(read_jsonl(args.source)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Källrader: {len(report['matching_records'])}")
    print(f"hv_only-rader: {len(report['hv_only_rows'])}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
