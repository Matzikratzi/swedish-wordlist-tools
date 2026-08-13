from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import (
    _normalized_key,
    _primary_text,
    _printed_form,
    _shared_siblings,
    classify_x_record,
)
from .compare_sources import _saol_upos
from .generate_adjective_forms import generated_row as generated_adjective_row
from .generate_noun_forms import canonical_noun_row
from .generate_verb_forms import generated_row as generated_verb_row
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-x-ambiguous-details.txt")
DEFAULT_JSON = Path("reports/saol14-x-ambiguous-details.json")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _generated_forms(record: dict[str, Any], upos: str) -> tuple[str, list[str]]:
    """Run the same canonical shared generator used elsewhere, when one exists."""

    row: dict[str, Any] | None
    if upos == "NOUN":
        row, _comparison = canonical_noun_row(record)
    elif upos == "ADJ":
        row = generated_adjective_row(record)
    elif upos == "VERB":
        row = generated_verb_row(record)
    elif upos == "PRON":
        return "no_shared_generator", []
    else:
        return "not_shared_class", []

    if row is None:
        return "unsupported", []
    forms = sorted(
        {
            str(form.get("written_form") or "")
            for form in row.get("forms", [])
            if form.get("written_form")
        },
        key=str.casefold,
    )
    return "generated", forms


def _candidate_detail(record: dict[str, Any]) -> dict[str, Any]:
    upos = _saol_upos(record)
    status, forms = _generated_forms(record, upos)
    return {
        "record_id": _record_id(record),
        "normaliserat_ord": clean_saol_word(record.get("normaliserat_ord")),
        "homonr": str(record.get("homonr") or ""),
        "ord": clean_saol_word(record.get("ord")),
        "stycke": str(record.get("stycke") or ""),
        "upos": upos,
        "source_upos": str(record.get("upos") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "text": _primary_text(record),
        "generated_status": status,
        "generated_forms": forms,
    }


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    siblings_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in materialized:
        key = _normalized_key(record)
        if key:
            siblings_by_key[key].append(record)

    cases: list[dict[str, Any]] = []
    class_pairs: Counter[str] = Counter()
    candidate_statuses: Counter[str] = Counter()

    for record in materialized:
        if str(record.get("upos") or "").upper() != "X":
            continue
        route, evidence = classify_x_record(record, siblings_by_key)
        if route != "ambiguous_hv_sibling_classes":
            continue

        candidates = [_candidate_detail(sibling) for sibling in _shared_siblings(record, siblings_by_key)]
        for candidate in candidates:
            candidate_statuses[candidate["generated_status"]] += 1
        classes = sorted({candidate["upos"] for candidate in candidates})
        class_pairs["/".join(classes)] += 1
        printed = _printed_form(record)
        cases.append({
            "record_id": _record_id(record),
            "lemma": clean_saol_word(record.get("normaliserat_ord")),
            "homonr": str(record.get("homonr") or ""),
            "printed_form": printed,
            "ordkl": str(record.get("ordkl") or ""),
            "text": _primary_text(record),
            "evidence_classes": list(evidence),
            "candidate_classes": classes,
            "candidates": candidates,
        })

    return {
        "ambiguous_records": len(cases),
        "class_pair_counts": dict(sorted(class_pairs.items())),
        "candidate_generator_statuses": dict(sorted(candidate_statuses.items())),
        "cases": cases,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14 X: detaljer för ambigua (hv)-poster",
        "",
        "Ingen routing ändras här. Rapporten visar den ambigua (hv)-raden, alla",
        "konkurrerande shared-huvudposter och vad respektive canonical generator",
        "faktiskt genererar från huvudpostens egen SAOL-notation.",
        "",
        f"Ambigua poster: {report['ambiguous_records']}",
        "Ordklasskombinationer:",
    ]
    for pair, count in report["class_pair_counts"].items():
        lines.append(f"  {count:3d}  {pair}")
    lines.append("Generatorstatus för kandidater:")
    for status, count in report["candidate_generator_statuses"].items():
        lines.append(f"  {count:3d}  {status}")

    for index, case in enumerate(report["cases"], start=1):
        lines.extend([
            "",
            "=" * 78,
            f"FALL {index:02d}: {case['lemma']} -> '{case['printed_form']}'",
            f"X: homonr={case['homonr']} id={case['record_id']} ordkl={case['ordkl']!r} text={case['text']!r}",
            f"Ambigua klasser: {', '.join(case['candidate_classes'])}",
        ])
        for candidate in case["candidates"]:
            lines.extend([
                f"  [{candidate['upos']}] homonr={candidate['homonr']} id={candidate['record_id']}",
                f"    ord={candidate['ord']!r} stycke={candidate['stycke']!r}",
                f"    ordkl={candidate['ordkl']!r}",
                f"    text={candidate['text']!r}",
                f"    generator={candidate['generated_status']}",
                "    former=" + (", ".join(candidate["generated_forms"]) if candidate["generated_forms"] else "(inga)"),
            ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect every ambiguous SAOL X homonym in detail")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ambigua (hv)-poster: {report['ambiguous_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
