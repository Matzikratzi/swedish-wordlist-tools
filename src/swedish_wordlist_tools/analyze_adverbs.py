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
DEFAULT_TEXT = Path("reports/saol14-adverb-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-adverb-analysis.json")


def _text(record: dict[str, Any]) -> str:
    value = record.get("text")
    if value is None or str(value).strip().casefold() in {"", "(null)", "null"}:
        return ""
    return str(value).strip()


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    variant_rows = 0
    for record in records:
        if _saol_upos(record) != "ADV":
            continue
        normal = clean_saol_word(record.get("normaliserat_ord"))
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        text = _text(record)
        variant = bool(normal and printed and normal.casefold() != printed.casefold())
        if variant:
            variant_rows += 1
        row = {
            "lemma": normal,
            "homonr": str(record.get("homonr") or ""),
            "ord": printed,
            "text": text,
            "text_length": len(text),
            "variant": variant,
            "ordkl": str(record.get("ordkl") or ""),
        }
        rows.append(row)
        groups[text or "<tom>"].append(row)

    counts = Counter({notation: len(items) for notation, items in groups.items()})
    return {
        "records": len(rows),
        "empty_text": sum(1 for row in rows if not row["text"]),
        "variant_rows": variant_rows,
        "unique_notations": len(groups),
        "groups": [
            {"notation": notation, "count": counts[notation], "examples": groups[notation][:12]}
            for notation in sorted(groups, key=lambda n: (-counts[n], n.casefold()))
        ],
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: inventering av ADV-notation",
        "",
        f"ADV-poster: {report['records']}",
        f"Poster utan text: {report['empty_text']}",
        f"Poster med tryckt ord != normaliserat_ord: {report['variant_rows']}",
        f"Unika notationsformer: {report['unique_notations']}",
        "",
        "Notationer (antal + exempel):",
        "",
    ]
    for group in report["groups"]:
        lines.append(f"[{group['count']:4d}] {group['notation']}")
        for row in group["examples"]:
            marker = " VARIANT" if row["variant"] else ""
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) ord='{row['ord']}'{marker} "
                f"len={row['text_length']} | {row['text']!r}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL adverb notation")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ADV-poster: {report['records']}")
    print(f"Poster utan text: {report['empty_text']}")
    print(f"Tryckta variantrader: {report['variant_rows']}")
    print(f"Unika notationsformer: {report['unique_notations']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
