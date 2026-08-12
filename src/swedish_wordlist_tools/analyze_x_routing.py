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
DEFAULT_TEXT = Path("reports/saol14-x-routing.txt")
DEFAULT_JSON = Path("reports/saol14-x-routing.json")

SHARED_CLASSES = frozenset({"NOUN", "ADJ", "VERB", "PRON"})


def _primary_text(record: dict[str, Any]) -> str:
    value = record.get("text")
    if value is None or str(value).strip().casefold() in {"", "(null)", "null"}:
        return ""
    return str(value).strip()


def _normalized_key(record: dict[str, Any]) -> str:
    return clean_saol_word(record.get("normaliserat_ord")).casefold()


def _ordkl_head(record: dict[str, Any]) -> str:
    return str(record.get("ordkl") or "").split("<", 1)[0].strip().casefold()


def _is_hv(record: dict[str, Any]) -> bool:
    return _ordkl_head(record).startswith("(hv)")


def _printed_form(record: dict[str, Any]) -> str:
    return clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))


def _text_mentions_form(record: dict[str, Any], form: str) -> bool:
    """Whether a sibling explicitly prints ``form`` in its inflection text."""

    text = _primary_text(record)
    if not text or not form:
        return False
    return re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text, re.IGNORECASE) is not None


def _shared_siblings(
    record: dict[str, Any], siblings_by_key: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    return [
        sibling
        for sibling in siblings_by_key.get(_normalized_key(record), [])
        if sibling is not record
        and str(sibling.get("upos") or "").upper() != "X"
        and _saol_upos(sibling) in SHARED_CLASSES
    ]


def classify_x_record(
    record: dict[str, Any],
    siblings_by_key: dict[str, list[dict[str, Any]]],
) -> tuple[str, tuple[str, ...]]:
    """Return a routing class plus concrete sibling evidence for one X row."""

    head = _ordkl_head(record)

    if head.startswith("adv. och adj.") and "oböjl" not in head:
        return "route_ADJ_shared_from_mixed_adv_adj", ()

    if head.startswith("(hv)"):
        siblings = _shared_siblings(record, siblings_by_key)
        sibling_classes = sorted({_saol_upos(sibling) for sibling in siblings})
        if len(sibling_classes) == 1:
            return f"route_{sibling_classes[0]}_shared_from_hv_sibling", tuple(sibling_classes)
        if len(sibling_classes) > 1:
            # Homonymous headwords can have several genuine word classes.  The
            # (hv) row's homonr is not a foreign key to one of them.  Instead,
            # use direct SAOL evidence: if its printed form occurs in exactly
            # one sibling class's inflection text, that class owns the form.
            form = _printed_form(record)
            matching_classes = sorted({
                _saol_upos(sibling)
                for sibling in siblings
                if _text_mentions_form(sibling, form)
            })
            if len(matching_classes) == 1:
                target = matching_classes[0]
                return f"route_{target}_shared_from_hv_sibling_form", (target,)
            return "ambiguous_hv_sibling_classes", tuple(sibling_classes)
        return "unresolved_hv_no_shared_sibling", ()

    resolved = _saol_upos(record)
    if resolved in SHARED_CLASSES:
        return f"route_{resolved}_shared_from_ordkl", (resolved,)
    if resolved == "ADV":
        return "remaining_ADV", (resolved,)
    if resolved == "NUM":
        return "remaining_NUM", (resolved,)
    if head.startswith(("best. artikel", "obest. artikel")):
        return "remaining_ARTICLE", ()
    return f"remaining_{resolved or 'X'}", (resolved,) if resolved else ()


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    siblings_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        key = _normalized_key(record)
        if key:
            siblings_by_key[key].append(record)

    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    without_text_hv = 0
    for record in materialized:
        if str(record.get("upos") or "").upper() != "X":
            continue
        text = _primary_text(record)
        if not text and not _is_hv(record):
            continue
        if not text:
            without_text_hv += 1
        route, evidence = classify_x_record(record, siblings_by_key)
        counts[route] += 1
        rows.append({
            "lemma": clean_saol_word(record.get("normaliserat_ord")),
            "homonr": str(record.get("homonr") or ""),
            "ord": clean_saol_word(record.get("ord")),
            "ordkl": str(record.get("ordkl") or ""),
            "text": text,
            "route": route,
            "evidence_classes": list(evidence),
        })

    return {
        "x_text_records": len(rows) - without_text_hv,
        "x_hv_records_without_text": without_text_hv,
        "x_routing_records": len(rows),
        "route_counts": dict(sorted(counts.items())),
        "shared_routable": sum(count for route, count in counts.items() if route.startswith("route_")),
        "ambiguous": counts.get("ambiguous_hv_sibling_classes", 0),
        "unresolved_hv": counts.get("unresolved_hv_no_shared_sibling", 0),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14 X: routingaudit mot verkliga ordklasser",
        "",
        "X är en export-/UPOS-restkategori, inte en grammatisk ordklass. (hv)-rader",
        "routas bara när samma normaliserade artikel har konkret huvudpostbevis.",
        "Vid homonyma huvudord används den tryckta (hv)-formen som direkt bevis",
        "om den förekommer i exakt en syskonordklass böjningstext.",
        "Blandade 'adv. och adj.' använder ADJ-shared för sin böjning.",
        "",
        f"X-poster med text: {report['x_text_records']}",
        f"(hv)-poster utan egen text: {report['x_hv_records_without_text']}",
        f"X-poster analyserade för routing: {report['x_routing_records']}",
        f"Direkt routbara till shared: {report['shared_routable']}",
        f"Ambigua (hv): {report['ambiguous']}",
        f"Olösta (hv): {report['unresolved_hv']}",
        "",
        "Routing:",
    ]
    for route, count in report["route_counts"].items():
        lines.append(f"  {count:4d}  {route}")

    lines.extend(["", "Exempel:"])
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report["rows"]:
        by_route[row["route"]].append(row)
    for route in sorted(by_route):
        lines.append(f"[{route}]")
        for row in by_route[route][:8]:
            evidence = ",".join(row["evidence_classes"]) or "-"
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) | ord='{row['ord']}' | "
                f"text='{row['text']}' | evidence={evidence}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit routing of SAOL UPOS X rows")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"X-poster med text: {report['x_text_records']}")
    print(f"(hv)-poster utan egen text: {report['x_hv_records_without_text']}")
    print(f"X-poster analyserade för routing: {report['x_routing_records']}")
    print(f"Direkt routbara till shared: {report['shared_routable']}")
    print(f"Ambigua (hv): {report['ambiguous']}")
    print(f"Olösta (hv): {report['unresolved_hv']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
