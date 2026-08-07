from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .generate_noun_forms import canonical_noun_row
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
# This command is now the canonical noun-artifact writer. If the artifact already
# exists, it is read first as the baseline so the impact report remains useful.
DEFAULT_BASELINE = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_JSONL = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-forms-grouped-impact.txt")
DEFAULT_SUMMARY = Path("reports/saol14-noun-forms-grouped-summary.json")

_SUP_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_PROVEN_NOTATION = "+det; pl. +, best. pl. +dena _ +t +n"


def clean_word(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return re.sub(r"\s+", " ", text).strip()


def record_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("subnr") or row.get("urspr_lopnr") or "")


def _representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return next((row for row in rows if str(row.get("homonr") or "") == "1"), rows[0])


def _proven_branch_bases(rows: list[dict[str, Any]]) -> tuple[str, str] | None:
    if not rows:
        return None
    representative = _representative(rows)
    if str(representative.get("text") or "").strip() != _PROVEN_NOTATION:
        return None
    if len({str(row.get("text") or "").strip() for row in rows}) != 1:
        return None
    if len({str(row.get("normaliserat_ord") or "").casefold() for row in rows}) != 1:
        return None
    main = str(representative.get("normaliserat_ord") or "").strip()
    variants = sorted(
        {clean_word(row.get("ord")) for row in rows if clean_word(row.get("ord"))},
        key=str.casefold,
    )
    if len(variants) != 2:
        return None
    matching = [variant for variant in variants if variant.casefold() == main.casefold()]
    if len(matching) != 1:
        return None
    alternative = next(variant for variant in variants if variant.casefold() != main.casefold())
    return main, alternative


def _form_dict(form: Any) -> dict[str, Any]:
    return {
        "written_form": form.written_form,
        "msd": str(form.msd) if form.msd is not None else None,
        "kind": form.kind,
        "source_stage": "noun_interpreter" if form.kind in {"lemma", "interpreted_slot"} else "noun_completion",
    }


def _grouped_row(source_row: dict[str, Any], bases: tuple[str, str]) -> dict[str, Any] | None:
    branches = ("+det; pl. +, best. pl. +dena", "+t +n")
    merged: list[Any] = []
    seen: set[tuple[str, str | None]] = set()
    for base, branch in zip(bases, branches):
        synthetic = dict(source_row)
        synthetic["normaliserat_ord"] = base
        synthetic["ord"] = base
        synthetic["text"] = branch
        # stycke belongs to the printed main headword. It is safe for the first
        # branch, but must not steer operations on the alternative base.
        if base.casefold() != str(source_row.get("normaliserat_ord") or "").casefold():
            synthetic["stycke"] = base
        entry = complete_noun_entry(synthetic, None)
        if entry is None:
            return None
        for form in entry.word_forms:
            marker = (form.written_form, str(form.msd) if form.msd is not None else None)
            if marker not in seen:
                seen.add(marker)
                merged.append(form)

    return {
        "completion_applied": True,
        "forms": [_form_dict(form) for form in merged],
        "homonym_number": str(source_row.get("homonr") or ""),
        "lemma": str(source_row.get("normaliserat_ord") or ""),
        "notation": str(source_row.get("text") or ""),
        "ordkl": str(source_row.get("ordkl") or ""),
        "pattern": str(source_row.get("text") or ""),
        "pattern_group": "grouped alternative ord bases",
        "record_id": record_id(source_row),
        "source": str(source_row.get("source") or ""),
        "stycke": str(source_row.get("stycke") or ""),
        "upos": "NOUN",
        "variant_bases": list(bases),
    }


def generate_grouped(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nouns = [row for row in records if _saol_upos(row) == "NOUN"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        groups[record_id(row)].append(row)

    output: list[dict[str, Any]] = []
    changed_groups = 0
    changed_rows = 0
    for _rid, rows in groups.items():
        bases = _proven_branch_bases(rows)
        if bases is not None:
            changed_groups += 1
        for source_row in rows:
            if bases is not None:
                row = _grouped_row(source_row, bases)
                if row is not None:
                    output.append(row)
                    changed_rows += 1
                    continue
            row, _comparison = canonical_noun_row(source_row)
            if row is not None:
                output.append(row)

    output.sort(key=lambda row: (str(row["lemma"]).casefold(), str(row["homonym_number"]), str(row["record_id"])))
    summary = {
        "noun_rows": len(nouns),
        "generated_rows": len(output),
        "proven_variant_groups": changed_groups,
        "proven_variant_rows": changed_rows,
        "canonical_form_rows": sum(len(row["forms"]) for row in output),
        "canonical_unique_written_forms": len({str(form["written_form"]).casefold() for row in output for form in row["forms"]}),
        "artifact": str(DEFAULT_JSONL),
        "scope": _PROVEN_NOTATION,
    }
    return output, summary


def _form_sets(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str], set[str]]:
    result: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        key = (str(row.get("record_id") or ""), str(row.get("homonym_number") or ""), str(row.get("lemma") or ""))
        result[key] = {str(form.get("written_form") or "") for form in row.get("forms", []) if form.get("written_form")}
    return result


def compare_to_baseline(new_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    new = _form_sets(new_rows)
    old = _form_sets(baseline_rows)
    impact: list[dict[str, Any]] = []
    for key in sorted(set(new) | set(old), key=lambda x: (x[2].casefold(), x[1], x[0])):
        before = old.get(key, set())
        after = new.get(key, set())
        if before == after:
            continue
        impact.append({
            "record_id": key[0],
            "homonym_number": key[1],
            "lemma": key[2],
            "added": sorted(after - before, key=str.casefold),
            "removed": sorted(before - after, key=str.casefold),
        })
    return impact


def render_impact(summary: dict[str, Any], impact: list[dict[str, Any]]) -> str:
    added = Counter(form for row in impact for form in row["added"])
    removed = Counter(form for row in impact for form in row["removed"])
    lines = [
        f"Bevisad struktur: {summary['scope']}",
        f"Påverkade artikelgrupper: {summary['proven_variant_groups']}",
        f"Påverkade rå-/artefaktrader: {summary['proven_variant_rows']}",
        f"Poster med ändrad formmängd mot baseline: {len(impact)}",
        f"Unika tillagda former: {len(added)}",
        f"Unika borttagna former: {len(removed)}",
        "",
        "Ändrade poster:",
    ]
    for row in impact:
        lines.append(f"  {row['lemma']} (homonr={row['homonym_number']}, record_id={row['record_id']})")
        lines.append("    + " + (", ".join(row["added"]) or "–"))
        lines.append("    - " + (", ".join(row["removed"]) or "–"))
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the canonical SAOL noun artifact with proven grouped ord-variant branches"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    # Read the old canonical artifact before overwriting it. This makes the
    # command safe when --baseline and --jsonl intentionally point to the same
    # official path.
    baseline_rows = list(read_jsonl(args.baseline)) if args.baseline.exists() else []
    rows, summary = generate_grouped(read_jsonl(args.saol))
    impact = compare_to_baseline(rows, baseline_rows) if baseline_rows else []

    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_impact(summary, impact), encoding="utf-8")
    summary = dict(summary, changed_against_baseline=len(impact), artifact=str(args.jsonl))
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Påverkade artikelgrupper: {summary['proven_variant_groups']}")
    print(f"Påverkade rader: {summary['proven_variant_rows']}")
    print(f"Ändrade mot baseline: {summary['changed_against_baseline']}")
    print(f"Officiell noun-artefakt: {args.jsonl}")
    print(f"Impact: {args.text}")


if __name__ == "__main__":
    main()
