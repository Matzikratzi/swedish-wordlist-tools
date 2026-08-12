from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _is_hv, _primary_text
from .compare_sources import _saol_upos
from .generate_adjective_forms import generated_row as generated_adjective_row
from .generate_noun_forms import canonical_noun_row
from .generate_verb_forms import generated_row as generated_verb_row
from .generate_x_routed_shared_forms import generate_rows as generate_x_rows
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-ignore-hv-audit.txt")
DEFAULT_JSON = Path("reports/saol14-ignore-hv-audit.json")


def _key(value: str) -> str:
    return value.casefold().strip()


def _real_generation_record(record: dict[str, Any]) -> dict[str, Any]:
    """Use a real row's printed spelling as inflection base when it is a variant.

    SAOL can export a full word-class row whose ``normaliserat_ord`` points to
    the canonical spelling while ``ord`` contains the spelling that the row's
    own notation actually belongs to.  The homonr=0 annexion row is the
    canonical example: normaliserat_ord=annektion, ord=annexion, text=+en +er.
    For this audit we must therefore test what that row itself can generate,
    rather than silently re-inflecting the normalized spelling.
    """

    printed = clean_saol_word(record.get("ord"))
    normalized = clean_saol_word(record.get("normaliserat_ord"))
    if not printed or not normalized or printed.casefold() == normalized.casefold():
        return record
    prepared = dict(record)
    prepared["normaliserat_ord"] = printed
    prepared["ord"] = printed
    prepared["stycke"] = printed
    return prepared


def _generated_real_forms(record: dict[str, Any]) -> set[str]:
    upos = _saol_upos(record)
    prepared = _real_generation_record(record)
    row: dict[str, Any] | None = None
    if upos == "NOUN":
        row, _comparison = canonical_noun_row(prepared)
    elif upos == "ADJ":
        row = generated_adjective_row(prepared)
    elif upos == "VERB":
        row = generated_verb_row(prepared)
    if row is None:
        return set()
    return {
        clean_saol_word(form.get("written_form"))
        for form in row.get("forms", [])
        if clean_saol_word(form.get("written_form"))
    }


def _text_mentions(text: str, form: str) -> bool:
    if not text or not form:
        return False
    return re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text, re.IGNORECASE) is not None


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    hv_records = [record for record in materialized if _is_hv(record)]
    real_records = [record for record in materialized if not _is_hv(record)]

    explicit_real: dict[str, list[dict[str, Any]]] = defaultdict(list)
    generated_real: dict[str, list[dict[str, Any]]] = defaultdict(list)
    real_texts: list[tuple[dict[str, Any], str]] = []

    for record in real_records:
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        if printed:
            explicit_real[_key(printed)].append(record)
        for form in _generated_real_forms(record):
            generated_real[_key(form)].append(record)
        text = _primary_text(record)
        if text:
            real_texts.append((record, text))

    x_rows, _summary = generate_x_rows(materialized)
    routed_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in x_rows:
        source_id = str(row.get("source_record_id") or "")
        routed_by_source[source_id].append(row)

    cases: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    unique_hv_forms: set[str] = set()
    unique_missing_forms: set[str] = set()

    for record in hv_records:
        source_id = str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")
        routed_forms = {
            clean_saol_word(form.get("written_form"))
            for row in routed_by_source.get(source_id, [])
            for form in row.get("forms", [])
            if clean_saol_word(form.get("written_form"))
        }
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        if printed:
            routed_forms.add(printed)

        for form in sorted(routed_forms, key=str.casefold):
            key = _key(form)
            unique_hv_forms.add(key)
            explicit_sources = explicit_real.get(key, [])
            generated_sources = generated_real.get(key, [])
            text_sources = [r for r, text in real_texts if _text_mentions(text, form)]
            if explicit_sources:
                status = "explicit_real_row"
                sources = explicit_sources
            elif generated_sources:
                status = "generated_from_real_row"
                sources = generated_sources
            elif text_sources:
                status = "mentioned_in_real_text"
                sources = text_sources
            else:
                status = "hv_only"
                sources = []
                unique_missing_forms.add(key)
            counts[status] += 1
            cases.append({
                "form": form,
                "status": status,
                "hv_record_id": source_id,
                "hv_lemma": clean_saol_word(record.get("normaliserat_ord")),
                "hv_homonr": str(record.get("homonr") or ""),
                "hv_ordkl": str(record.get("ordkl") or ""),
                "source_rows": [
                    {
                        "ord": clean_saol_word(source.get("ord")),
                        "normaliserat_ord": clean_saol_word(source.get("normaliserat_ord")),
                        "homonr": str(source.get("homonr") or ""),
                        "upos": _saol_upos(source),
                        "ordkl": str(source.get("ordkl") or ""),
                        "text": _primary_text(source),
                    }
                    for source in sources[:5]
                ],
            })

    return {
        "hv_records": len(hv_records),
        "real_records": len(real_records),
        "audited_form_occurrences": len(cases),
        "unique_hv_forms": len(unique_hv_forms),
        "unique_hv_only_forms": len(unique_missing_forms),
        "status_counts": dict(sorted(counts.items())),
        "cases": cases,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: audit av hypotesen att ignorera alla (hv)-rader",
        "",
        "Varje form som en (hv)-rad bidrar med jämförs mot alla icke-(hv)-rader.",
        "När en riktig rad har annan tryckt ordform än normaliserat_ord böjs den",
        "från den tryckta formen; raden behandlas alltså som ett eget variantparadigm.",
        "Återfunnen = egen riktig rad, genererad från riktig NOUN/ADJ/VERB-rad,",
        "eller explicit nämnd i en riktig rads text. hv_only är den verkliga restmängden.",
        "",
        f"(hv)-poster: {report['hv_records']}",
        f"Icke-(hv)-poster: {report['real_records']}",
        f"Auditerade formförekomster: {report['audited_form_occurrences']}",
        f"Unika (hv)-former: {report['unique_hv_forms']}",
        f"Unika former som bara finns via (hv): {report['unique_hv_only_forms']}",
        "Status:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:5d}  {status}")

    for status in ("hv_only", "mentioned_in_real_text", "generated_from_real_row", "explicit_real_row"):
        matching = [case for case in report["cases"] if case["status"] == status]
        lines.extend(["", "=" * 78, f"{status}: {len(matching)}"])
        for case in matching[:250]:
            source_desc = "; ".join(
                f"{source['upos']} {source['normaliserat_ord']}({source['homonr']}) text={source['text']!r}"
                for source in case["source_rows"]
            ) or "-"
            lines.append(f"  {case['form']!r} <- hv {case['hv_lemma']}({case['hv_homonr']}) | {source_desc}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether SAOL (hv) rows can be ignored safely")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"(hv)-poster: {report['hv_records']}")
    print(f"Unika (hv)-former: {report['unique_hv_forms']}")
    print(f"Unika former bara via (hv): {report['unique_hv_only_forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
