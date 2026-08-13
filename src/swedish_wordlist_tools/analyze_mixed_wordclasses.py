from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-mixed-wordclasses.txt")
DEFAULT_JSON = Path("reports/saol14-mixed-wordclasses.json")

MARKERS = (
    ("NOUN", ("subst", "substantiv", "s.")),
    ("VERB", ("verb", "v.", "rxv", "ptv")),
    ("ADJ", ("adj", "adjektiv")),
    ("ADV", ("adv",)),
    ("PRON", ("pron",)),
    ("NUM", ("räkn", "räkneord")),
    ("PROPN", ("namn",)),
    ("INTJ", ("interj",)),
    ("ADP", ("prep",)),
    ("CCONJ", ("samordnande", "konj")),
    ("SCONJ", ("underordnande", "subj")),
)


def _head(record: dict[str, Any]) -> str:
    return str(record.get("ordkl") or "").split("<", 1)[0].strip().casefold()


def classes_from_head(head: str) -> tuple[str, ...]:
    classes: list[str] = []
    for upos, markers in MARKERS:
        for marker in markers:
            if marker in {"s.", "v."}:
                import re
                if re.search(rf"(?:^|\s){re.escape(marker)}(?:\s|$)", head):
                    classes.append(upos)
                    break
            elif marker in head:
                classes.append(upos)
                break
    return tuple(dict.fromkeys(classes))


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    head_counts: Counter[str] = Counter()
    combo_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        head = _head(record)
        if not head:
            continue
        classes = classes_from_head(head)
        if len(classes) < 2:
            continue
        combo = "+".join(classes)
        head_counts[head] += 1
        combo_counts[combo] += 1
        row = {
            "ord": record.get("ord"),
            "normaliserat_ord": record.get("normaliserat_ord"),
            "homonr": record.get("homonr"),
            "ordkl_head": head,
            "classes": list(classes),
            "text": record.get("text"),
            "upos_export": record.get("upos"),
            "record_id": record.get("subnr") or record.get("urspr_lopnr"),
        }
        rows.append(row)
        if len(examples[head]) < 10:
            examples[head].append(row)
    return {
        "mixed_records": len(rows),
        "unique_heads": len(head_counts),
        "combination_counts": dict(sorted(combo_counts.items())),
        "head_counts": dict(sorted(head_counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples": examples,
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: blandade ordklasser i ordkl-huvudet",
        "",
        f"Blandklassposter: {report['mixed_records']}",
        f"Unika ordkl-huvuden: {report['unique_heads']}",
        "",
        "Kombinationer:",
    ]
    for combo, count in report["combination_counts"].items():
        lines.append(f"  {count:5d}  {combo}")
    lines.extend(["", "Ordkl-huvuden:"])
    for head, count in report["head_counts"].items():
        lines.append(f"\n[{count:5d}] {head}")
        for row in report["examples"][head]:
            lines.append(
                f"  {row['ord']!r} norm={row['normaliserat_ord']!r} hom={row['homonr']} "
                f"classes={','.join(row['classes'])} upos={row['upos_export']} text={row['text']!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit mixed SAOL word-class heads")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    serializable = dict(report)
    serializable["examples"] = {key: value for key, value in report["examples"].items()}
    args.json.write_text(json.dumps(serializable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Blandklassposter: {report['mixed_records']}")
    print(f"Unika ordkl-huvuden: {report['unique_heads']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
