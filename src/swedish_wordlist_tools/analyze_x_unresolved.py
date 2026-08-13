from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _normalized_key, _primary_text, _printed_form, classify_x_record
from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-x-unresolved-details.txt")
DEFAULT_JSON = Path("reports/saol14-x-unresolved-details.json")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _detail(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": _record_id(record),
        "normaliserat_ord": clean_saol_word(record.get("normaliserat_ord")),
        "homonr": str(record.get("homonr") or ""),
        "ord": clean_saol_word(record.get("ord")),
        "stycke": str(record.get("stycke") or ""),
        "upos": _saol_upos(record),
        "source_upos": str(record.get("upos") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "text": _primary_text(record),
    }


def _shape(record: dict[str, Any], non_x_siblings: list[dict[str, Any]]) -> str:
    lemma = clean_saol_word(record.get("normaliserat_ord"))
    printed = _printed_form(record)
    if lemma.startswith("-") or lemma.endswith("-") or printed.startswith("-") or printed.endswith("-"):
        return "affix_or_bound_form"
    if non_x_siblings:
        return "nonshared_sibling"
    if lemma and printed and lemma.casefold() != printed.casefold():
        return "variant_without_non_x_sibling"
    return "no_non_x_sibling"


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    siblings_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        key = _normalized_key(record)
        if key:
            siblings_by_key[key].append(record)

    cases: list[dict[str, Any]] = []
    shapes: Counter[str] = Counter()
    sibling_class_sets: Counter[str] = Counter()

    for record in materialized:
        if str(record.get("upos") or "").upper() != "X":
            continue
        route, _evidence = classify_x_record(record, siblings_by_key)
        if route != "unresolved_hv_no_shared_sibling":
            continue

        siblings = [s for s in siblings_by_key.get(_normalized_key(record), []) if s is not record]
        non_x = [s for s in siblings if str(s.get("upos") or "").upper() != "X"]
        x_siblings = [s for s in siblings if str(s.get("upos") or "").upper() == "X"]
        classes = sorted({_saol_upos(s) or "?" for s in non_x})
        shape = _shape(record, non_x)
        shapes[shape] += 1
        sibling_class_sets["/".join(classes) if classes else "(none)"] += 1

        cases.append({
            "record_id": _record_id(record),
            "lemma": clean_saol_word(record.get("normaliserat_ord")),
            "homonr": str(record.get("homonr") or ""),
            "printed_form": _printed_form(record),
            "ordkl": str(record.get("ordkl") or ""),
            "text": _primary_text(record),
            "shape": shape,
            "non_x_classes": classes,
            "non_x_siblings": [_detail(s) for s in non_x],
            "x_siblings": [_detail(s) for s in x_siblings],
        })

    cases.sort(key=lambda row: (row["shape"], row["lemma"].casefold(), row["printed_form"].casefold()))
    return {
        "unresolved_records": len(cases),
        "shape_counts": dict(sorted(shapes.items())),
        "non_x_class_set_counts": dict(sorted(sibling_class_sets.items())),
        "cases": cases,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14 X: detaljer för olösta (hv) utan shared-syskon",
        "",
        "Ingen routing ändras här. 'Olöst' betyder bara att NOUN/ADJ/VERB/PRON-syskon",
        "saknas. Rapporten visar om samma normaliserade artikel ändå har en annan",
        "icke-X-ordklass, eller om posten verkligen saknar en icke-X-huvudpost.",
        "",
        f"Olösta poster: {report['unresolved_records']}",
        "Struktur:",
    ]
    for shape, count in report["shape_counts"].items():
        lines.append(f"  {count:3d}  {shape}")
    lines.append("Icke-X-syskonklasser:")
    for classes, count in report["non_x_class_set_counts"].items():
        lines.append(f"  {count:3d}  {classes}")

    for index, case in enumerate(report["cases"], start=1):
        lines.extend([
            "",
            "=" * 78,
            f"FALL {index:02d}: {case['lemma']} -> '{case['printed_form']}'",
            f"X: homonr={case['homonr']} id={case['record_id']} shape={case['shape']}",
            f"   ordkl={case['ordkl']!r} text={case['text']!r}",
            "Icke-X-syskon: " + (", ".join(case["non_x_classes"]) if case["non_x_classes"] else "(inga)"),
        ])
        for sibling in case["non_x_siblings"]:
            lines.extend([
                f"  [{sibling['upos'] or '?'}] homonr={sibling['homonr']} id={sibling['record_id']}",
                f"    ord={sibling['ord']!r} stycke={sibling['stycke']!r}",
                f"    ordkl={sibling['ordkl']!r} text={sibling['text']!r}",
            ])
        if case["x_siblings"]:
            lines.append("  Andra X-syskon:")
            for sibling in case["x_siblings"]:
                lines.append(
                    f"    homonr={sibling['homonr']} ord={sibling['ord']!r} "
                    f"ordkl={sibling['ordkl']!r} text={sibling['text']!r}"
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect unresolved SAOL X (hv) records")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Olösta (hv): {report['unresolved_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
