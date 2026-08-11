from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .generate_noun_forms import DEFAULT_SAOL
from .jsonl import read_jsonl
from .noun_paradigm import (
    _complete_from_slots,
    _entry_from_interpreted_row,
    _has_unmarked_replacement,
    _has_usable_compound_bar,
    _lemma_only_entry,
    _replacement_is_explicit_plural_use,
    complete_noun_entry,
)
from .noun_source_errors import noun_lemma_only_source_error
from .noun_truncated_shared import interpret_truncated_noun_row
from .saol_noun_variants import prepare_noun_variant_records
from .saol_row_interpreter import interpret_noun_row
from .saol_source_policy import is_truncated_inflection_source

DEFAULT_TEXT = Path("reports/saol14-noun-truncated-delta.txt")
DEFAULT_JSON = Path("reports/saol14-noun-truncated-delta.json")


def _previous_complete_noun_entry(record: dict[str, Any]):
    """Emulate noun completion immediately before shared truncated-prefix recovery.

    This intentionally mirrors the ca1c17a behavior: truncated rows still used
    the ordinary row interpreter; missing definite plural was not derived for a
    truncated source.
    """

    if str(record.get("upos") or "").upper() != "NOUN":
        return None

    source_error = noun_lemma_only_source_error(record)
    if source_error is not None:
        return _lemma_only_entry(record, source_error)

    row = interpret_noun_row(record)
    if row is None:
        return None
    if (
        _has_unmarked_replacement(row)
        and not _has_usable_compound_bar(record, row.lemma)
        and not _replacement_is_explicit_plural_use(record)
    ):
        return None

    return _complete_from_slots(
        _entry_from_interpreted_row(row),
        derive_missing_plural_definite=False,
    )


def _form_dict(form) -> dict[str, str]:
    return {
        "written_form": str(form.written_form),
        "msd": str(form.msd) if form.msd is not None else "",
        "kind": str(form.kind),
    }


def _form_key(form) -> tuple[str, str, str]:
    item = _form_dict(form)
    return item["written_form"], item["msd"], item["kind"]


def _recovered_key_forms(record: dict[str, Any]) -> list[dict[str, str]]:
    row = interpret_truncated_noun_row(record)
    if row is None:
        return []
    return [
        {
            "slot": key_form.slot,
            "written_form": key_form.written_form,
            "source_token": key_form.source,
        }
        for key_form in row.key_forms
    ]


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    truncated_records = 0
    before_records = 0
    after_records = 0
    before_forms = 0
    after_forms = 0

    for record in records:
        if str(record.get("upos") or "").upper() != "NOUN":
            continue
        if not is_truncated_inflection_source(record):
            continue
        truncated_records += 1

        before = _previous_complete_noun_entry(record)
        after = complete_noun_entry(record, None)
        if before is not None:
            before_records += 1
            before_forms += len(before.word_forms)
        if after is not None:
            after_records += 1
            after_forms += len(after.word_forms)

        before_keys = {_form_key(form) for form in before.word_forms} if before else set()
        after_keys = {_form_key(form) for form in after.word_forms} if after else set()
        added_keys = after_keys - before_keys
        removed_keys = before_keys - after_keys
        if before is not None and after is not None and not added_keys and not removed_keys:
            continue
        if before is None and after is None:
            continue

        added = [
            {"written_form": word, "msd": msd, "kind": kind}
            for word, msd, kind in sorted(added_keys, key=lambda item: (item[0].casefold(), item[1], item[2]))
        ]
        removed = [
            {"written_form": word, "msd": msd, "kind": kind}
            for word, msd, kind in sorted(removed_keys, key=lambda item: (item[0].casefold(), item[1], item[2]))
        ]
        rows.append(
            {
                "record_id": str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or ""),
                "lemma": str(record.get("normaliserat_ord") or ""),
                "homonym_number": str(record.get("homonr") or ""),
                "text": str(record.get("text") or ""),
                "ordkl": str(record.get("ordkl") or ""),
                "stycke": str(record.get("stycke") or ""),
                "before_generated": before is not None,
                "after_generated": after is not None,
                "before_form_count": len(before.word_forms) if before else 0,
                "after_form_count": len(after.word_forms) if after else 0,
                "added_forms": added,
                "removed_forms": removed,
                "recovered_key_forms": _recovered_key_forms(record),
            }
        )

    rows.sort(key=lambda row: (row["lemma"].casefold(), row["homonym_number"], row["record_id"]))
    return {
        "truncated_records": truncated_records,
        "before_generated_records": before_records,
        "after_generated_records": after_records,
        "generated_record_delta": after_records - before_records,
        "before_form_rows": before_forms,
        "after_form_rows": after_forms,
        "form_row_delta": after_forms - before_forms,
        "changed_truncated_records": len(rows),
        "rows": rows,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: effekt av shared prefix-tolkning för trunkerade källrader",
        "",
        "Före emulerar beteendet i ca1c17a. Efter använder nuvarande generator.",
        "Endast poster som klassas som trunkerade av saol_source_policy ingår.",
        "Ingen SALDO-data används.",
        "",
        f"Trunkerade poster: {summary['truncated_records']}",
        f"Genererade poster före: {summary['before_generated_records']}",
        f"Genererade poster efter: {summary['after_generated_records']}",
        f"Delta poster: {summary['generated_record_delta']:+d}",
        f"Formrader före: {summary['before_form_rows']}",
        f"Formrader efter: {summary['after_form_rows']}",
        f"Delta formrader: {summary['form_row_delta']:+d}",
        f"Trunkerade poster med ändrad output: {summary['changed_truncated_records']}",
    ]

    for index, row in enumerate(summary["rows"], start=1):
        homonym = f" ({row['homonym_number']})" if row["homonym_number"] else ""
        lines.extend(
            [
                "",
                f"{index}. {row['lemma']}{homonym} | id={row['record_id']}",
                f"   text={row['text']!r}",
                f"   före: {'genererad' if row['before_generated'] else 'ej genererad'} ({row['before_form_count']} formrader)",
                f"   efter: {'genererad' if row['after_generated'] else 'ej genererad'} ({row['after_form_count']} formrader)",
            ]
        )
        if row["recovered_key_forms"]:
            lines.append("   säkert återvunna key forms:")
            for form in row["recovered_key_forms"]:
                lines.append(
                    f"     {form['slot']}: {form['written_form']} <- {form['source_token']!r}"
                )
        if row["added_forms"]:
            lines.append("   tillkomna formrader:")
            for form in row["added_forms"]:
                lines.append(
                    f"     {form['written_form']} | {form['msd']} | {form['kind']}"
                )
        if row["removed_forms"]:
            lines.append("   borttagna formrader:")
            for form in row["removed_forms"]:
                lines.append(
                    f"     {form['written_form']} | {form['msd']} | {form['kind']}"
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    records = prepare_noun_variant_records(read_jsonl(args.saol))
    summary = build_summary(records)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(summary), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Trunkerade poster: {summary['truncated_records']}")
    print(f"Delta poster: {summary['generated_record_delta']:+d}")
    print(f"Delta formrader: {summary['form_row_delta']:+d}")
    print(f"Ändrade trunkerade poster: {summary['changed_truncated_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
