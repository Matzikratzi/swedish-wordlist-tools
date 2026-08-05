from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .inflect import GeneratedEntry, GeneratedWordForm, generate_entry
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry
from .saol_row_interpreter import interpret_noun_row

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSONL = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-forms-summary.json")
DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-comparison.jsonl")
DEFAULT_COMPARISON_TEXT = Path("reports/saol14-noun-forms-comparison.txt")


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _form_key(form: GeneratedWordForm) -> tuple[str, str | None]:
    return (
        form.written_form.casefold(),
        str(form.msd) if form.msd is not None else None,
    )


def _form_dict(form: GeneratedWordForm, stage: str) -> dict[str, Any]:
    return {
        "written_form": form.written_form,
        "msd": str(form.msd) if form.msd is not None else None,
        "kind": form.kind,
        "source_stage": stage,
    }


def _unsupported_comparison(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": _record_id(record),
        "lemma": str(record.get("normaliserat_ord", "")),
        "homonym_number": str(record.get("homonr", "")),
        "notation": str(record.get("text", "")),
        "status": "unsupported",
        "legacy_forms": [],
        "canonical_forms": [],
        "added_by_completion": [],
        "removed_by_completion": [],
    }


def canonical_noun_row(record: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if _saol_upos(record) != "NOUN":
        return None, None

    # The generic legacy generator accepts any sequence of word-like tokens as
    # explicit forms. For nouns, the row interpreter is the authority on
    # whether the text is actually valid SAOL inflection notation.
    if interpret_noun_row(record) is None:
        return None, _unsupported_comparison(record)

    initial = generate_entry(record)
    completed = complete_noun_entry(record, initial)
    canonical = completed or initial
    if canonical is None:
        return None, _unsupported_comparison(record)

    initial_forms = tuple(initial.word_forms if initial is not None else ())
    canonical_forms = tuple(canonical.word_forms)
    initial_keys = {_form_key(form) for form in initial_forms}
    canonical_keys = {_form_key(form) for form in canonical_forms}

    forms = [
        _form_dict(form, "base_generator" if _form_key(form) in initial_keys else "noun_completion")
        for form in canonical_forms
    ]
    row = {
        "record_id": _record_id(record),
        "lemma": canonical.lemma,
        "homonym_number": str(record.get("homonr", "")),
        "upos": "NOUN",
        "ordkl": str(record.get("ordkl", "")),
        "notation": str(record.get("text", "")),
        "stycke": str(record.get("stycke", "")),
        "source": str(record.get("source", "")),
        "pattern": canonical.pattern,
        "pattern_group": canonical.pattern_group,
        "completion_applied": canonical_keys != initial_keys,
        "forms": forms,
    }

    initial_written = {form.written_form for form in initial_forms}
    canonical_written = {form.written_form for form in canonical_forms}
    comparison = {
        "record_id": row["record_id"],
        "lemma": row["lemma"],
        "homonym_number": row["homonym_number"],
        "notation": row["notation"],
        "status": (
            "unchanged"
            if initial_written == canonical_written
            else "completion_changed_forms"
        ),
        "legacy_forms": sorted(initial_written, key=str.casefold),
        "canonical_forms": sorted(canonical_written, key=str.casefold),
        "added_by_completion": sorted(canonical_written - initial_written, key=str.casefold),
        "removed_by_completion": sorted(initial_written - canonical_written, key=str.casefold),
    }
    return row, comparison


def generate_noun_artifact(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    noun_records = 0

    for record in records:
        if _saol_upos(record) != "NOUN":
            continue
        noun_records += 1
        row, comparison = canonical_noun_row(record)
        if row is not None:
            rows.append(row)
        if comparison is not None:
            comparisons.append(comparison)

    rows.sort(key=lambda row: (str(row["lemma"]).casefold(), str(row["homonym_number"]), str(row["record_id"])))
    comparisons.sort(key=lambda row: (str(row["status"]), str(row["lemma"]).casefold(), str(row["record_id"])))

    status_counts = Counter(str(row["status"]) for row in comparisons)
    form_kind_counts = Counter(
        str(form["kind"])
        for row in rows
        for form in row["forms"]
    )
    stage_counts = Counter(
        str(form["source_stage"])
        for row in rows
        for form in row["forms"]
    )
    canonical_written = {
        str(form["written_form"]).casefold()
        for row in rows
        for form in row["forms"]
        if form.get("written_form")
    }
    added_written = {
        str(form).casefold()
        for row in comparisons
        for form in row["added_by_completion"]
    }
    removed_written = {
        str(form).casefold()
        for row in comparisons
        for form in row["removed_by_completion"]
    }

    summary = {
        "noun_records": noun_records,
        "generated_noun_records": len(rows),
        "unsupported_noun_records": status_counts.get("unsupported", 0),
        "canonical_form_rows": sum(len(row["forms"]) for row in rows),
        "canonical_unique_written_forms": len(canonical_written),
        "comparison_status_counts": dict(sorted(status_counts.items())),
        "form_kind_counts": dict(sorted(form_kind_counts.items())),
        "source_stage_counts": dict(sorted(stage_counts.items())),
        "unique_forms_added_by_completion": len(added_written),
        "unique_forms_removed_by_completion": len(removed_written),
    }
    return rows, comparisons, summary


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def render_comparison(summary: dict[str, Any], comparisons: list[dict[str, Any]]) -> str:
    counts = summary["comparison_status_counts"]
    lines = [
        f"Substantivposter: {summary['noun_records']}",
        f"Kanoniskt genererade poster: {summary['generated_noun_records']}",
        f"Poster utan stödd notation: {summary['unsupported_noun_records']}",
        f"Kanoniska formrader: {summary['canonical_form_rows']}",
        f"Unika skrivna former: {summary['canonical_unique_written_forms']}",
        f"Oförändrade mot grundgeneratorn: {counts.get('unchanged', 0)}",
        f"Ändrade av substantivkompletteringen: {counts.get('completion_changed_forms', 0)}",
        f"Unika former tillagda av kompletteringen: {summary['unique_forms_added_by_completion']}",
        f"Unika former borttagna av kompletteringen: {summary['unique_forms_removed_by_completion']}",
    ]
    changed = [row for row in comparisons if row["status"] == "completion_changed_forms"]
    if changed:
        lines.extend(["", "Exempel på skillnader:"])
        for row in changed[:50]:
            added = ", ".join(row["added_by_completion"]) or "-"
            removed = ", ".join(row["removed_by_completion"]) or "-"
            lines.append(
                f"  {row['lemma']} | {row['notation']} | tillagt: {added} | borttaget: {removed}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a canonical SAOL noun-form artifact and compare it with the legacy base generator"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--comparison-text", type=Path, default=DEFAULT_COMPARISON_TEXT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows, comparisons, summary = generate_noun_artifact(read_jsonl(args.saol))
    _write_jsonl(args.jsonl, rows)
    _write_jsonl(args.comparison, comparisons)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.comparison_text.write_text(render_comparison(summary, comparisons), encoding="utf-8")

    print(f"Substantivposter: {summary['noun_records']}")
    print(f"Kanoniskt genererade poster: {summary['generated_noun_records']}")
    print(f"Kanoniska formrader: {summary['canonical_form_rows']}")
    print(f"JSONL: {args.jsonl}")
    print(f"Jämförelse: {args.comparison_text}")


if __name__ == "__main__":
    main()
