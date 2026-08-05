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
DEFAULT_JSONL = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-forms-summary.json")
DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-comparison.jsonl")
DEFAULT_COMPARISON_TEXT = Path("reports/saol14-noun-forms-comparison.txt")

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
        return "unchanged"
    if legacy < canonical:
        return "more_forms"
    if canonical < legacy:
        return "fewer_forms"
    return "changed_forms"


def _direct_operation_reasons(record: dict[str, Any]) -> dict[str, str]:
    row = interpret_noun_row(record)
    if row is None:
        return {}
    reasons: dict[str, str] = {}
    for key_form in row.key_forms:
        if key_form.slot == "lemma":
            reasons[key_form.written_form.casefold()] = "lemma"
            continue
        operation = parse_form_operation(key_form.source)
        reasons[key_form.written_form.casefold()] = (
            operation.kind.value if operation is not None else "interpreted_slot"
        )
    return reasons


def _change_reasons(
    record: dict[str, Any],
    canonical_forms: tuple[GeneratedWordForm, ...],
    added: set[str],
) -> dict[str, str]:
    direct = _direct_operation_reasons(record)
    reasons: dict[str, str] = {}
    for form in canonical_forms:
        if form.written_form not in added:
            continue
        reason = direct.get(form.written_form.casefold())
        if reason is None:
            reason = {
                "derived_genitive": "derived_genitive",
                "derived_definite_plural": "derived_definite_plural",
            }.get(form.kind, form.kind)
        reasons[form.written_form] = reason
    return dict(sorted(reasons.items(), key=lambda item: item[0].casefold()))


def _normalised_words(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"\s+", value.casefold().strip()) if part)


def _has_suffix_on_wrong_phrase_word(form: str, lemma: str) -> bool:
    """Detect the legacy bug that appended a noun suffix to phrase word one."""

    lemma_words = _normalised_words(lemma)
    form_words = _normalised_words(form)
    if len(lemma_words) < 2 or len(form_words) != len(lemma_words):
        return False
    return (
        form_words[1:] == lemma_words[1:]
        and form_words[0].startswith(lemma_words[0])
        and len(form_words[0]) > len(lemma_words[0])
    )


def _is_single_duplicated_segment(form: str, canonical: str) -> bool:
    """Return true when deleting one adjacent duplicate repairs the old form."""

    old = form.casefold()
    new = canonical.casefold()
    if len(old) <= len(new):
        return False
    excess = len(old) - len(new)
    for split in range(len(new) + 1):
        suffix_length = len(new) - split
        if not old.startswith(new[:split]):
            continue
        if suffix_length and not old.endswith(new[split:]):
            continue
        end = len(old) - suffix_length if suffix_length else len(old)
        duplicated = old[split:end]
        if len(duplicated) != excess or not duplicated:
            continue
        if new[:split].endswith(duplicated) or new[split:].startswith(duplicated):
            return True
    return False


def _removed_form_reason(
    form: str,
    lemma: str,
    added_forms: set[str],
) -> str:
    normalized = re.sub(r"[^0-9a-zåäöéü-]+", "", form.casefold())
    if normalized in _LEGACY_COMMENT_TOKENS:
        return "legacy_comment_token"
    folded_lemma = lemma.casefold()
    if normalized and len(normalized) < len(folded_lemma) and folded_lemma.startswith(normalized):
        return "legacy_truncated_token"
    if _has_suffix_on_wrong_phrase_word(form, lemma):
        return "legacy_malformed_form"
    if any(_is_single_duplicated_segment(form, candidate) for candidate in added_forms):
        return "legacy_malformed_form"
    return "semantic_difference"


def _removed_form_reasons(
    removed: set[str],
    lemma: str,
    added_forms: set[str],
) -> dict[str, str]:
    return dict(
        sorted(
            (
                (form, _removed_form_reason(form, lemma, added_forms))
                for form in removed
            ),
            key=lambda item: item[0].casefold(),
        )
    )


def canonical_noun_row(record: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if _saol_upos(record) != "NOUN":
        return None, None

    canonical = complete_noun_entry(record, None)
    if canonical is None:
        return None, _unsupported_comparison(record)

    legacy = generate_entry(record)
    legacy_forms = tuple(legacy.word_forms if legacy is not None else ())
    canonical_forms = tuple(canonical.word_forms)
    legacy_written = {form.written_form for form in legacy_forms}
    canonical_written = {form.written_form for form in canonical_forms}
    added = canonical_written - legacy_written
    removed = legacy_written - canonical_written
    removed_reasons = _removed_form_reasons(removed, canonical.lemma, added)
    legacy_noise = {
        form for form, reason in removed_reasons.items() if reason.startswith("legacy_")
    }
    legacy_malformed = {
        form
        for form, reason in removed_reasons.items()
        if reason == "legacy_malformed_form"
    }
    semantic_removed = removed - legacy_noise

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
        "completion_applied": any(form.kind not in {"lemma", "interpreted_slot"} for form in canonical_forms),
        "forms": [_form_dict(form) for form in canonical_forms],
    }
    comparison = {
        "record_id": row["record_id"],
        "lemma": row["lemma"],
        "homonym_number": row["homonym_number"],
        "notation": row["notation"],
        "stycke": row["stycke"],
        "status": _comparison_status(legacy_written, canonical_written),
        "legacy_forms": sorted(legacy_written, key=str.casefold),
        "canonical_forms": sorted(canonical_written, key=str.casefold),
        "added_forms": sorted(added, key=str.casefold),
        "removed_forms": sorted(removed, key=str.casefold),
        "change_reasons": _change_reasons(record, canonical_forms, added),
        "removed_form_reasons": removed_reasons,
        "legacy_noise_removed_forms": sorted(legacy_noise, key=str.casefold),
        "legacy_malformed_removed_forms": sorted(legacy_malformed, key=str.casefold),
        "semantic_removed_forms": sorted(semantic_removed, key=str.casefold),
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
    reason_counts = Counter(
        str(reason)
        for row in comparisons
        for reason in row.get("change_reasons", {}).values()
    )
    removed_reason_counts = Counter(
        str(reason)
        for row in comparisons
        for reason in row.get("removed_form_reasons", {}).values()
    )
    form_kind_counts = Counter(str(form["kind"]) for row in rows for form in row["forms"])
    stage_counts = Counter(str(form["source_stage"]) for row in rows for form in row["forms"])
    canonical_written = {
        str(form["written_form"]).casefold()
        for row in rows for form in row["forms"] if form.get("written_form")
    }
    added_written = {
        str(form).casefold() for row in comparisons for form in row.get("added_forms", [])
    }
    removed_written = {
        str(form).casefold() for row in comparisons for form in row.get("removed_forms", [])
    }
    legacy_noise_written = {
        str(form).casefold()
        for row in comparisons
        for form in row.get("legacy_noise_removed_forms", [])
    }
    legacy_malformed_written = {
        str(form).casefold()
        for row in comparisons
        for form in row.get("legacy_malformed_removed_forms", [])
    }
    semantic_removed_written = {
        str(form).casefold()
        for row in comparisons
        for form in row.get("semantic_removed_forms", [])
    }
    summary = {
        "noun_records": noun_records,
        "generated_noun_records": len(rows),
        "unsupported_noun_records": status_counts.get("unsupported", 0),
        "canonical_form_rows": sum(len(row["forms"]) for row in rows),
        "canonical_unique_written_forms": len(canonical_written),
        "comparison_status_counts": dict(sorted(status_counts.items())),
        "change_reason_counts": dict(sorted(reason_counts.items())),
        "removed_form_reason_counts": dict(sorted(removed_reason_counts.items())),
        "form_kind_counts": dict(sorted(form_kind_counts.items())),
        "source_stage_counts": dict(sorted(stage_counts.items())),
        "unique_forms_added": len(added_written),
        "unique_forms_removed": len(removed_written),
        "unique_legacy_noise_removed": len(legacy_noise_written),
        "unique_legacy_malformed_removed": len(legacy_malformed_written),
        "unique_semantic_forms_removed": len(semantic_removed_written),
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
        f"Oförändrade: {counts.get('unchanged', 0)}",
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
        description="Generate canonical SAOL noun forms and a semantic diff against the legacy generator"
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
