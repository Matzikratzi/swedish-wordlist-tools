from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_noun_mismatch_patterns import _suffix_pattern, read_jsonl
from .compare_sources import _key, _saol_upos, read_saldo
from .jsonl import read_jsonl as read_source_jsonl
from .validate_direct_forms import _record_forms

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_JSON = Path("reports/saol14-top-noun-mismatch-groups.json")
DEFAULT_TEXT = Path("reports/saol14-top-noun-mismatch-groups.txt")


def _folded(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values if str(value)}


def _group_key(row: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    lemma = str(row.get("lemma", ""))
    return (
        _suffix_pattern(lemma, row.get("extra_from_saol", [])),
        _suffix_pattern(lemma, row.get("missing_from_saol", [])),
    )


def build_saol_form_index(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        lemma = str(record.get("normaliserat_ord", "")).strip()
        upos = _saol_upos(record)
        forms = _record_forms(record)
        if not lemma or not upos or not forms:
            continue
        entry = {
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "lemma": lemma,
            "homonym_number": str(record.get("homonr", "")),
            "upos": upos,
            "notation": str(record.get("text", "")),
            "forms": sorted(forms, key=str.casefold),
        }
        for form in _folded(forms):
            index[form].append(entry)
    return index


def _other_saol_entries(
    row: dict[str, Any],
    form_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    current_id = str(row.get("record_id", ""))
    missing = _folded(row.get("missing_from_saol", []))
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for form in missing:
        for entry in form_index.get(form, []):
            if entry["record_id"] == current_id:
                continue
            marker = (entry["record_id"], entry["lemma"], entry["upos"])
            item = found.setdefault(marker, {
                "record_id": entry["record_id"],
                "lemma": entry["lemma"],
                "homonym_number": entry["homonym_number"],
                "upos": entry["upos"],
                "notation": entry["notation"],
                "overlapping_missing_forms": [],
            })
            item["overlapping_missing_forms"].append(form)
    result = list(found.values())
    for item in result:
        item["overlapping_missing_forms"] = sorted(set(item["overlapping_missing_forms"]))
    result.sort(key=lambda item: (-len(item["overlapping_missing_forms"]), item["lemma"].casefold(), item["upos"]))
    return result


def analyse(
    validation_rows: Iterable[dict[str, Any]],
    saol_records: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
    top_groups: int = 20,
) -> dict[str, Any]:
    rows = [row for row in validation_rows if row.get("status") == "form_set_mismatch" and row.get("upos") == "NOUN"]
    grouped: dict[tuple[tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)
    ranked = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[:top_groups]
    form_index = build_saol_form_index(saol_records)

    groups: list[dict[str, Any]] = []
    for (extra_pattern, missing_pattern), members in ranked:
        details: list[dict[str, Any]] = []
        for row in sorted(members, key=lambda value: (str(value.get("lemma", "")).casefold(), str(value.get("homonym_number", "")))):
            lemma = str(row.get("lemma", ""))
            analyses = [analysis for analysis in saldo.get(_key(lemma), []) if analysis.get("upos") == "NOUN"]
            details.append({
                "lemma": lemma,
                "homonym_number": str(row.get("homonym_number", "")),
                "record_id": str(row.get("record_id", "")),
                "notation": str(row.get("notation", "")),
                "generated_forms": list(row.get("generated_forms", [])),
                "saldo_forms": list(row.get("saldo_forms", [])),
                "extra_from_saol": list(row.get("extra_from_saol", [])),
                "missing_from_saol": list(row.get("missing_from_saol", [])),
                "saldo_analyses": [
                    {
                        "id": str(analysis.get("id", "")),
                        "lemmas": sorted(str(value) for value in analysis.get("lemmas", [])),
                        "upos": str(analysis.get("upos", "")),
                        "forms": sorted((str(value) for value in analysis.get("forms", [])), key=str.casefold),
                    }
                    for analysis in analyses
                ],
                "other_saol_entries": _other_saol_entries(row, form_index),
            })
        groups.append({
            "count": len(members),
            "extra_pattern": list(extra_pattern),
            "missing_pattern": list(missing_pattern),
            "entries": details,
        })
    return {
        "remaining_noun_mismatches": len(rows),
        "total_groups": len(grouped),
        "reported_groups": len(groups),
        "groups": groups,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Kvarvarande substantivmismatch: {summary['remaining_noun_mismatches']}",
        f"Substantivgrupper totalt: {summary['total_groups']}",
        f"Visade största grupper: {summary['reported_groups']}",
    ]
    for number, group in enumerate(summary["groups"], start=1):
        lines.extend([
            "",
            f"=== GRUPP {number}: {group['count']} poster ===",
            "Extra: " + (", ".join(group["extra_pattern"]) or "–"),
            "Saknas: " + (", ".join(group["missing_pattern"]) or "–"),
        ])
        for entry in group["entries"]:
            suffix = f" ({entry['homonym_number']})" if entry["homonym_number"] else ""
            lines.extend([
                "",
                f"Ord: {entry['lemma']}{suffix}",
                f"Notation: {entry['notation']}",
                "SAOL-former: " + ", ".join(entry["generated_forms"]),
                "SALDO-former: " + ", ".join(entry["saldo_forms"]),
                "Extra från SAOL: " + (", ".join(entry["extra_from_saol"]) or "–"),
                "Saknas från SAOL: " + (", ".join(entry["missing_from_saol"]) or "–"),
            ])
            if entry["other_saol_entries"]:
                lines.append("Andra SAOL-artiklar med saknade former:")
                for other in entry["other_saol_entries"]:
                    lines.append(
                        f"  {other['lemma']} ({other['upos']}, homonym {other['homonym_number'] or '–'}): "
                        + ", ".join(other["overlapping_missing_forms"])
                    )
            else:
                lines.append("Andra SAOL-artiklar med saknade former: –")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Detaljanalysera de största kvarvarande substantivmismatchgrupperna")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--top-groups", type=int, default=20)
    args = parser.parse_args()
    if args.top_groups < 1:
        raise SystemExit("--top-groups måste vara minst 1")
    summary = analyse(read_jsonl(args.validation), read_source_jsonl(args.saol), read_saldo(args.saldo), args.top_groups)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(summary), encoding="utf-8")
    print(f"Kvarvarande substantivmismatch: {summary['remaining_noun_mismatches']}")
    print(f"Analyserade grupper: {summary['reported_groups']} av {summary['total_groups']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
