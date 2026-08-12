from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _normalized_key, _primary_text, classify_x_record
from .generate_adjective_forms import generated_row as generated_adjective_row
from .generate_noun_forms import canonical_noun_row
from .generate_verb_forms import generated_row as generated_verb_row
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-x-routed-shared-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-x-routed-shared-forms-summary.json")
DEFAULT_TEXT = Path("reports/saol14-x-routed-shared-forms.txt")

_CANONICAL_ORDKL = {
    "NOUN": "subst.",
    "ADJ": "adj.",
    "VERB": "verb",
    "PRON": "pron.",
}
_ADJ_RELATION_SLOTS = {
    "komp.": "comparative",
    "superl.": "superlative",
}


def _target_from_route(route: str) -> str | None:
    if not route.startswith("route_") or "_shared_" not in route:
        return None
    return route[len("route_") :].split("_shared_", 1)[0]


def _routed_base(record: dict[str, Any], route: str) -> str:
    """Return the printed spelling whose inflection notation belongs to this row."""

    if "_from_hv_sibling" in route:
        written = clean_saol_word(record.get("ord"))
        if written:
            return written
    return clean_saol_word(record.get("normaliserat_ord")) or clean_saol_word(record.get("ord"))


def routed_record(record: dict[str, Any], route: str, target: str) -> dict[str, Any] | None:
    base = _routed_base(record, route)
    if not base or target not in _CANONICAL_ORDKL:
        return None
    prepared = dict(record)
    prepared["_saol_x_source_upos"] = str(record.get("upos") or "")
    prepared["_saol_x_source_ordkl"] = str(record.get("ordkl") or "")
    prepared["_saol_x_source_normaliserat_ord"] = str(record.get("normaliserat_ord") or "")
    prepared["_saol_x_route"] = route
    prepared["normaliserat_ord"] = base
    prepared["ord"] = base
    prepared["stycke"] = base
    prepared["upos"] = target
    prepared["ordkl"] = _CANONICAL_ORDKL[target]
    return prepared


def _generate_direct_hv_form(record: dict[str, Any], route: str, target: str) -> dict[str, Any] | None:
    """Preserve a textless (hv) row as the explicit printed form it represents."""

    if _primary_text(record) or "_from_hv_sibling" not in route:
        return None
    written = clean_saol_word(record.get("ord"))
    if not written:
        return None
    return {
        "lemma": written,
        "forms": [{
            "written_form": written,
            "slot": "explicit_hv_form",
            "provenance": "explicit_hv_form",
            "source_token": "",
            "operation_base": written,
        }],
        "relation_only": True,
    }


def _generate_relation_row(record: dict[str, Any], route: str, target: str) -> dict[str, Any] | None:
    """Return a direct form when an (hv) row labels its printed spelling's role."""

    # The routing suffix describes how the class was established, not whether
    # the row is a relation.  Once the printed form has resolved a homonym we
    # can still have notation such as ``komp.`` on that same row (färre -> få).
    if target != "ADJ" or "_from_hv_sibling" not in route:
        return None
    notation = " ".join(_primary_text(record).casefold().split())
    slot = _ADJ_RELATION_SLOTS.get(notation)
    if slot is None:
        return None
    base = _routed_base(record, route)
    if not base:
        return None
    return {
        "lemma": base,
        "forms": [{
            "written_form": base,
            "slot": slot,
            "provenance": "explicit_hv_relation",
            "source_token": notation,
            "operation_base": base,
        }],
        "relation_only": True,
    }


def _generate_target_row(record: dict[str, Any], target: str) -> dict[str, Any] | None:
    if target == "NOUN":
        row, _comparison = canonical_noun_row(record)
        return row
    if target == "ADJ":
        return generated_adjective_row(record)
    if target == "VERB":
        return generated_verb_row(record)
    return None


def generate_rows(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    materialized = [dict(record) for record in records]
    siblings_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        key = _normalized_key(record)
        if key:
            siblings_by_key[key].append(record)

    rows: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    generated_counts: Counter[str] = Counter()
    relation_only = 0
    failed: list[dict[str, Any]] = []

    for source in materialized:
        if str(source.get("upos") or "").upper() != "X":
            continue
        route, evidence = classify_x_record(source, siblings_by_key)
        target = _target_from_route(route)
        if target is None:
            continue
        route_counts[route] += 1

        generated = _generate_direct_hv_form(source, route, target)
        if generated is None:
            generated = _generate_relation_row(source, route, target)
        if generated is not None and generated.get("relation_only"):
            relation_only += 1
        elif generated is None:
            prepared = routed_record(source, route, target)
            generated = _generate_target_row(prepared, target) if prepared is not None else None

        if generated is None:
            failed.append({
                "lemma": clean_saol_word(source.get("normaliserat_ord")),
                "ord": clean_saol_word(source.get("ord")),
                "homonr": str(source.get("homonr") or ""),
                "target_upos": target,
                "route": route,
                "text": _primary_text(source),
                "evidence_classes": list(evidence),
            })
            continue

        generated_counts[target] += 1
        rows.append({
            "source_record_id": str(source.get("id") or source.get("subnr") or source.get("urspr_lopnr") or ""),
            "source_normaliserat_ord": clean_saol_word(source.get("normaliserat_ord")),
            "source_ord": clean_saol_word(source.get("ord")),
            "source_ordkl": str(source.get("ordkl") or ""),
            "source_text": _primary_text(source),
            "homonym_number": str(source.get("homonr") or ""),
            "target_upos": target,
            "route": route,
            "routed_lemma": str(generated.get("lemma") or ""),
            "relation_only": bool(generated.get("relation_only")),
            "forms": list(generated.get("forms") or []),
        })

    unique_forms = {
        str(form.get("written_form") or "").casefold()
        for row in rows
        for form in row["forms"]
        if form.get("written_form")
    }
    summary = {
        "routable_records": sum(route_counts.values()),
        "generated_records": len(rows),
        "failed_records": len(failed),
        "relation_only_records": relation_only,
        "generated_by_target": dict(sorted(generated_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "generated_form_rows": sum(len(row["forms"]) for row in rows),
        "unique_written_forms": len(unique_forms),
        "failed": failed,
    }
    return rows, summary


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 X: verklig shared-generering efter routing",
        "",
        "Routade X-rader med notation körs genom samma NOUN/ADJ/VERB-shared-generator",
        "som den verifierade huvudordklassen. Textlösa (hv)-rader är redan explicit",
        "formbevis och bevaras därför direkt i den ordklass som routingen fastställt.",
        "Homonyma fall routas bara när den tryckta formen finns i exakt en syskonordklass.",
        "",
        f"Routbara poster: {summary['routable_records']}",
        f"Genererade poster: {summary['generated_records']}",
        f"Varav direkta/relationsposter: {summary['relation_only_records']}",
        f"Misslyckade poster: {summary['failed_records']}",
        f"Genererade formrader: {summary['generated_form_rows']}",
        f"Unika skrivna former: {summary['unique_written_forms']}",
        "",
        "Genererade per målordklass:",
    ]
    for target, count in summary["generated_by_target"].items():
        lines.append(f"  {count:4d}  {target}")
    lines.extend(["", "Misslyckade routade poster:"])
    if not summary["failed"]:
        lines.append("  (inga)")
    else:
        for row in summary["failed"]:
            lines.append(
                f"  {row['lemma']} ({row['homonr']}) | ord='{row['ord']}' | "
                f"target={row['target_upos']} | text='{row['text']}'"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate routed SAOL X rows through shared interpreters")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    rows, summary = generate_rows(read_jsonl(args.source))
    write_jsonl(args.jsonl, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.write_text(render_text(summary), encoding="utf-8")
    print(f"Routbara X-poster: {summary['routable_records']}")
    print(f"Genererade X-poster via shared: {summary['generated_records']}")
    print(f"Varav direkta/relationsposter: {summary['relation_only_records']}")
    print(f"Misslyckade routade poster: {summary['failed_records']}")
    print(f"Genererade formrader: {summary['generated_form_rows']}")
    print(f"Unika skrivna former: {summary['unique_written_forms']}")
    print(f"JSONL: {args.jsonl}")
    print(f"Text: {args.text}")


if __name__ == "__main__":
    main()
