from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-pronoun-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-pronoun-analysis.json")


def _text(record: dict[str, Any]) -> str:
    value = record.get("text")
    if value is None or str(value).strip().casefold() in {"", "null", "(null)"}:
        return ""
    return str(value).strip()


def _notation_shape(text: str) -> str:
    value = text.casefold().strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\b[0-9]+\b", "#", value)
    return value


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    shape_counts: Counter[str] = Counter()
    empty_text = 0
    printed_variant_rows = 0

    for source in records:
        record = dict(source)
        if _saol_upos(record) != "PRON":
            continue
        text = _text(record)
        printed = clean_saol_word(record.get("ord"))
        normalized = clean_saol_word(record.get("normaliserat_ord"))
        is_printed_variant = bool(printed and normalized and printed.casefold() != normalized.casefold())
        if is_printed_variant:
            printed_variant_rows += 1
        if not text:
            empty_text += 1
        shape = _notation_shape(text)
        shape_counts[shape] += 1
        rows.append({
            "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
            "lemma": normalized,
            "ord": printed,
            "homonr": str(record.get("homonr") or ""),
            "ordkl": str(record.get("ordkl") or ""),
            "text": text,
            "text_length": len(text),
            "notation_shape": shape,
            "printed_variant": is_printed_variant,
        })

    rows.sort(key=lambda row: (row["notation_shape"], row["lemma"].casefold(), row["homonr"], row["record_id"]))
    examples_by_shape: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if len(examples_by_shape[row["notation_shape"]]) < 12:
            examples_by_shape[row["notation_shape"]].append(row)

    return {
        "pronoun_records": len(rows),
        "empty_text_records": empty_text,
        "printed_variant_records": printed_variant_rows,
        "notation_shapes": len(shape_counts),
        "shape_counts": dict(sorted(shape_counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples_by_shape": dict(examples_by_shape),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: inventering av PRON-notation",
        "",
        f"PRON-poster: {report['pronoun_records']}",
        f"Poster utan text: {report['empty_text_records']}",
        f"Poster med tryckt ord != normaliserat_ord: {report['printed_variant_records']}",
        f"Unika notationsformer: {report['notation_shapes']}",
        "",
        "Notationer (antal + exempel):",
    ]
    for shape, count in report["shape_counts"].items():
        label = shape if shape else "<tom>"
        lines.append("")
        lines.append(f"[{count:4d}] {label}")
        for row in report["examples_by_shape"].get(shape, []):
            variant = " VARIANT" if row["printed_variant"] else ""
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) ord={row['ord']!r}{variant} "
                f"len={row['text_length']} | {row['text']!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL pronoun notation before implementing PRON generation")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PRON-poster: {report['pronoun_records']}")
    print(f"Poster utan text: {report['empty_text_records']}")
    print(f"Tryckta variantrader: {report['printed_variant_records']}")
    print(f"Unika notationsformer: {report['notation_shapes']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
