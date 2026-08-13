from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-numeral-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-numeral-analysis.json")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    notation_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    empty_text = 0
    printed_variants = 0
    lengths: Counter[int] = Counter()

    for record in records:
        if _saol_upos(record) != "NUM":
            continue
        text = _value(record, "text").strip()
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        normalized = clean_saol_word(record.get("normaliserat_ord"))
        variant = bool(printed and normalized and printed.casefold() != normalized.casefold())
        if not text:
            empty_text += 1
        if variant:
            printed_variants += 1
        lengths[len(text)] += 1
        row = {
            "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
            "lemma": normalized,
            "homonr": _value(record, "homonr"),
            "ord": printed,
            "ordkl": _value(record, "ordkl"),
            "text": text,
            "text_length": len(text),
            "printed_variant": variant,
        }
        rows.append(row)
        notation_groups[text].append(row)

    grouped = []
    for notation, items in sorted(notation_groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        grouped.append({"notation": notation, "count": len(items), "examples": items[:12]})

    return {
        "numeral_records": len(rows),
        "empty_text_records": empty_text,
        "printed_variant_records": printed_variants,
        "unique_notations": len(notation_groups),
        "text_length_counts": dict(sorted(lengths.items())),
        "groups": grouped,
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: inventering av NUM-notation",
        "",
        f"NUM-poster: {report['numeral_records']}",
        f"Poster utan text: {report['empty_text_records']}",
        f"Poster med tryckt ord != normaliserat_ord: {report['printed_variant_records']}",
        f"Unika notationsformer: {report['unique_notations']}",
        "",
        "Notationer (antal + exempel):",
        "",
    ]
    for group in report["groups"]:
        notation = group["notation"] or "<tom>"
        lines.append(f"[{group['count']:4d}] {notation}")
        for row in group["examples"]:
            variant = " VARIANT" if row["printed_variant"] else ""
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) ord='{row['ord']}'{variant} "
                f"len={row['text_length']} | '{row['text']}'"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL numeral notation before shared interpretation")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NUM-poster: {report['numeral_records']}")
    print(f"Poster utan text: {report['empty_text_records']}")
    print(f"Tryckta variantrader: {report['printed_variant_records']}")
    print(f"Unika notationsformer: {report['unique_notations']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
