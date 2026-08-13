from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_current_hv_only import analyze as analyze_current_hv_only
from .analyze_x_routing import _is_hv, _primary_text
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word
from .saol_wordclasses import classes_from_record

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-hv-unknowns.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-hv-unknowns.json")


def _key(value: Any) -> str:
    return clean_saol_word(value).casefold().strip()


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    current = analyze_current_hv_only(materialized)

    targets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        if _is_hv(record):
            continue
        lemma = _key(record.get("normaliserat_ord"))
        if lemma:
            targets[lemma].append(record)

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    notation_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()

    for item in current["remaining"]:
        if item.get("classification") != "UNKNOWN_WORD":
            continue
        lemma = _key(item.get("hv_lemma"))
        target_rows = targets.get(lemma, [])
        target_classes: set[str] = set()
        notations: set[str] = set()
        for record in target_rows:
            target_classes.update(classes_from_record(record))
            text = _primary_text(record)
            if text:
                notations.add(text)
        if not target_classes:
            target_classes.add("UNKNOWN_TARGET")
        for cls in target_classes:
            class_counts[cls] += 1
        for notation in notations or {"<tom>"}:
            notation_counts[notation] += 1
        gap = str(item.get("gap_hypothesis") or "")
        if gap:
            gap_counts[gap] += 1
        rows.append({
            "form": item.get("form"),
            "hv_lemma": item.get("hv_lemma"),
            "gap_hypothesis": gap,
            "target_classes": sorted(target_classes),
            "target_notations": sorted(notations),
        })

    rows.sort(key=lambda row: str(row["form"]).casefold())
    return {
        "unknown_forms": len(rows),
        "target_class_counts": dict(sorted(class_counts.items())),
        "gap_counts": dict(sorted(gap_counts.items())),
        "notation_counts": dict(sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: gruppering av kvarvarande verkliga hv-UNKNOWN",
        "",
        f"UNKNOWN-former: {report['unknown_forms']}",
        "",
        "Efter målordklass:",
    ]
    for cls, count in report["target_class_counts"].items():
        lines.append(f"  {count:4d}  {cls}")
    lines.extend(["", "Efter gap-hypotes:"])
    for gap, count in report["gap_counts"].items():
        lines.append(f"  {count:4d}  {gap}")
    lines.extend(["", "Vanligaste målnotationer:"])
    for notation, count in list(report["notation_counts"].items())[:40]:
        lines.append(f"  {count:4d}  {notation}")

    lines.extend(["", "=" * 78, "Poster"])
    for row in report["rows"]:
        classes = ",".join(row["target_classes"])
        notations = " | ".join(row["target_notations"]) or "<tom>"
        lines.append(
            f"  {row['form']!r} <- {row['hv_lemma']} | {row['gap_hypothesis']} | "
            f"classes={classes} | text={notations!r}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Group remaining current hv UNKNOWN forms")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Kvarvarande hv-UNKNOWN: {report['unknown_forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
