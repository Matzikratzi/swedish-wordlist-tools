from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .inflect import GeneratedWordForm, generate_entry
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry
from .saol_notation import parse_form_operation
from .saol_row_interpreter import interpret_noun_row

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
# Row-wise generation is retained for diagnostics/regression comparison only.
# The official noun artifact is written by generate_noun_forms_grouped.
DEFAULT_JSONL = Path("reports/saol14-noun-forms-rowwise.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-forms-rowwise-summary.json")
DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-rowwise-comparison.jsonl")
DEFAULT_COMPARISON_TEXT = Path("reports/saol14-noun-forms-rowwise-comparison.txt")

_LEGACY_COMMENT_TOKENS = frozenset(
    {
        "anv",
        "användas",
        "används",
        "i",
        "kan",
        "ofta",
        "som",
        "undviks",
        "vanl",
    }
)


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _form_key(form: GeneratedWordForm) -> tuple[str, str | None]:
    return form.written_form.casefold(), str(form.msd) if form.msd is not None else None


def _canonical_stage(form: GeneratedWordForm) -> str:
    return "noun_interpreter" if form.kind in {"lemma", "interpreted_slot"} else "noun_completion"


def _form_dict(form: GeneratedWordForm) -> dict[str, Any]:
    return {
        "written_form": form.written_form,
        "msd": str(form.msd) if form.msd is not None else None,
        "kind": form.kind,
        "source_stage": _canonical_stage(form),
    }


def _unsupported_comparison(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": _record_id(record),
        "lemma": str(record.get("normaliserat_ord", "")),
        "homonym_number": str(record.get("homonr", "")),
        "notation": str(record.get("text", "")),
        "stycke": str(record.get("stycke", "")),
        "status": "unsupported",
        "legacy_forms": [],
        "canonical_forms": [],
        "added_forms": [],
        "removed_forms": [],
        "change_reasons": {},
        "removed_form_reasons": {},
        "legacy_noise_removed_forms": [],
        "legacy_malformed_removed_forms": [],
        "semantic_removed_forms": [],
    }


def _comparison_status(legacy: set[str], canonical: set[str]) -> str:
    if legacy == canonical:
        return "same"
    if legacy < canonical:
        return "more_forms"
    if canonical < legacy:
        return "fewer_forms"
    return "changed_forms"


def _is_legacy_comment_token(form: str) -> bool:
    return form.casefold() in _LEGACY_COMMENT_TOKENS


def _is_legacy_malformed_form(form: str) -> bool:
    return bool(
        re.search(r"[<>{}\[\]|_]", form)
        or form.startswith(("+", "-"))
        or form.endswith(("+", "-"))
        or "  " in form
    )


def _change_reason(form: GeneratedWordForm) -> str:
    return str(form.kind or "unknown")


def canonical_noun_row(record: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if _saol_upos(record) != "NOUN":
        return None, _unsupported_comparison(record)

    entry = complete_noun_entry(record, None)
    if entry is None:
        return None, _unsupported_comparison(record)

    canonical_forms = list(entry.word_forms)
    canonical_set = {form.written_form for form in canonical_forms}

    legacy_entry = generate_entry(record)
    legacy_forms = list(legacy_entry.word_forms) if legacy_entry is not None else []
    legacy_set = {form.written_form for form in legacy_forms}

    removed = sorted(legacy_set - canonical_set, key=str.casefold)
    added = sorted(canonical_set - legacy_set, key=str.casefold)
    legacy_noise = sorted((form for form in removed if _is_legacy_comment_token(form)), key=str.casefold)
    malformed = sorted((form for form in removed if _is_legacy_malformed_form(form)), key=str.casefold)
    semantic = sorted(set(removed) - set(legacy_noise) - set(malformed), key=str.casefold)

    reason_by_form = {form.written_form: _change_reason(form) for form in canonical_forms if form.written_form in added}
    comparison = {
        "record_id": _record_id(record),
        "lemma": str(record.get("normaliserat_ord", "")),
        "homonym_number": str(record.get("homonr", "")),
        "notation": str(record.get("text", "")),
        "stycke": str(record.get("stycke", "")),
        "status": _comparison_status(legacy_set, canonical_set),
        "legacy_forms": sorted(legacy_set, key=str.casefold),
        "canonical_forms": sorted(canonical_set, key=str.casefold),
        "added_forms": added,
        "removed_forms": removed,
        "change_reasons": reason_by_form,
        "removed_form_reasons": {
            form: (
                "legacy_comment_token" if form in legacy_noise else
                "legacy_malformed_form" if form in malformed else
                "semantic_difference"
            )
            for form in removed
        },
        "legacy_noise_removed_forms": legacy_noise,
        "legacy_malformed_removed_forms": malformed,
        "semantic_removed_forms": semantic,
    }
    row = {
        "completion_applied": True,
        "forms": [_form_dict(form) for form in canonical_forms],
        "homonym_number": str(record.get("homonr") or ""),
        "lemma": str(record.get("normaliserat_ord") or ""),
        "notation": str(record.get("text") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "pattern": str(record.get("text") or ""),
        "pattern_group": "interpreted noun slots",
        "record_id": _record_id(record),
        "source": str(record.get("source") or ""),
        "stycke": str(record.get("stycke") or ""),
        "upos": "NOUN",
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
        comparisons.append(comparison)
        if row is not None:
            rows.append(row)

    status_counts = Counter(row["status"] for row in comparisons)
    added_forms = {form for row in comparisons for form in row["added_forms"]}
    removed_forms = {form for row in comparisons for form in row["removed_forms"]}
    noise_removed = {form for row in comparisons for form in row["legacy_noise_removed_forms"]}
    malformed_removed = {form for row in comparisons for form in row["legacy_malformed_removed_forms"]}
    semantic_removed = {form for row in comparisons for form in row["semantic_removed_forms"]}
    reason_counts = Counter(reason for row in comparisons for reason in row["change_reasons"].values())
    removed_reason_counts = Counter(reason for row in comparisons for reason in row["removed_form_reasons"].values())

    summary = {
        "noun_records": noun_records,
        "generated_noun_records": len(rows),
        "unsupported_noun_records": status_counts.get("unsupported", 0),
        "canonical_form_rows": sum(len(row["forms"]) for row in rows),
        "canonical_unique_written_forms": len({form["written_form"].casefold() for row in rows for form in row["forms"]}),
        "comparison_status_counts": dict(sorted(status_counts.items())),
        "change_reason_counts": dict(sorted(reason_counts.items())),
        "removed_form_reason_counts": dict(sorted(removed_reason_counts.items())),
        "unique_forms_added": len(added_forms),
        "unique_forms_removed": len(removed_forms),
        "unique_legacy_noise_removed": len(noise_removed),
        "unique_legacy_malformed_removed": len(malformed_removed),
        "unique_semantic_forms_removed": len(semantic_removed),
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
        "OBS: diagnostisk rad-för-rad-generator; officiell noun-artefakt skrivs av generate_noun_forms_grouped.",
        f"Substantivposter: {summary['noun_records']}",
        f"Genererade poster: {summary['generated_noun_records']}",
        f"Oförändrade: {counts.get('same', 0)}",
        f"Fler former: {counts.get('more_forms', 0)}",
        f"Färre former: {counts.get('fewer_forms', 0)}",
        f"Både tillagda och borttagna: {counts.get('changed_forms', 0)}",
        f"Unika tillagda former: {summary['unique_forms_added']}",
        f"Unika borttagna former: {summary['unique_forms_removed']}",
        f"Varav gammalt generatorskräp: {summary['unique_legacy_noise_removed']}",
        f"Varav tydligt felformade gamla former: {summary['unique_legacy_malformed_removed']}",
        f"Semantiskt borttagna former: {summary['unique_semantic_forms_removed']}",
        "Orsaker till tillägg: " + ", ".join(
            f"{reason}={count}" for reason, count in summary["change_reason_counts"].items()
        ),
        "Orsaker till borttagning: " + ", ".join(
            f"{reason}={count}" for reason, count in summary["removed_form_reason_counts"].items()
        ),
    ]
    for status, heading in (
        ("more_forms", "Poster med fler former"),
        ("fewer_forms", "Poster med färre former"),
        ("changed_forms", "Poster med ändrade former"),
        ("unsupported", "Poster utan stödd notation"),
    ):
        selected = [row for row in comparisons if row["status"] == status]
        if not selected:
            continue
        lines.extend(["", f"{heading} ({len(selected)}):"])
        for row in selected[:100]:
            added = ", ".join(row.get("added_forms", [])) or "-"
            removed = ", ".join(row.get("removed_forms", [])) or "-"
            noise = ", ".join(row.get("legacy_noise_removed_forms", [])) or "-"
            malformed = ", ".join(row.get("legacy_malformed_removed_forms", [])) or "-"
            semantic = ", ".join(row.get("semantic_removed_forms", [])) or "-"
            reasons = ", ".join(
                f"{form}:{reason}" for form, reason in row.get("change_reasons", {}).items()
            ) or "-"
            lines.append(
                f"  {row['lemma']} | {row['notation']} | stycke={row.get('stycke', '')} | "
                f"tillagt: {added} | borttaget: {removed} | generatorskräp: {noise} | "
                f"felformade gamla former: {malformed} | semantiskt borttaget: {semantic} | "
                f"orsaker: {reasons}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnostic row-wise SAOL noun generation; official artifact uses article variants"
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
    print("OBS: diagnostisk rad-för-rad-generator. Officiell noun-artefakt byggs med generate_noun_forms_grouped.")
    print(f"Substantivposter: {summary['noun_records']}")
    print(f"Kanoniskt genererade poster: {summary['generated_noun_records']}")
    print(f"Kanoniska formrader: {summary['canonical_form_rows']}")
    print(f"Diagnostisk JSONL: {args.jsonl}")
    print(f"Jämförelse: {args.comparison_text}")


if __name__ == "__main__":
    main()
