from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical_direct_forms import canonical_record_forms
from .canonical_form_artifacts import (
    DEFAULT_ADJECTIVE_FORMS,
    DEFAULT_NOUN_FORMS,
    forms_from_artifacts,
    load_word_class_artifacts,
    read_artifact_variant_paradigms,
    variant_paradigms_from_artifact,
)
from .jsonl import read_jsonl
from .revalidate_direct_forms_core import (
    ARTIFACT_WORD_CLASSES,
    canonical_validation_row,
    select_article_variant_match_from_artifacts,
    select_direct_match_from_artifacts,
)
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, build_form_index, read_saldo_forms
from .validate_direct_forms import DEFAULT_SAOL, _form_status

DEFAULT_JSONL = Path("reports/saol14-article-variant-matching-impact.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-article-variant-matching-impact-summary.json")
DEFAULT_TEXT = Path("reports/saol14-article-variant-matching-impact.txt")


def _analysis_forms(analyses: list[dict[str, Any]]) -> set[str]:
    return {
        str(form)
        for analysis in analyses
        for form in analysis.get("forms", ())
        if form
    }


def _status(generated_forms: set[str], analyses: list[dict[str, Any]]) -> str:
    return _form_status(generated_forms, _analysis_forms(analyses), bool(generated_forms))


def analyze(
    saol_path: Path = DEFAULT_SAOL,
    saldo_forms_path: Path = DEFAULT_SALDO_FORMS,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    saldo = read_saldo_forms(saldo_forms_path)
    form_index = build_form_index(saldo)
    artifacts = load_word_class_artifacts(noun_path=noun_forms_path, adjective_path=adjective_forms_path)
    noun_variant_paradigms = read_artifact_variant_paradigms(noun_forms_path)

    rows: list[dict[str, Any]] = []
    transition_counts: Counter[str] = Counter()
    method_transition_counts: Counter[str] = Counter()
    variant_records = 0
    changed_match = 0
    changed_status = 0
    mismatch_delta = 0

    for record in read_jsonl(saol_path):
        upos = str(record.get("upos") or "").upper()
        if upos != "NOUN":
            continue

        paradigms = variant_paradigms_from_artifact(record, noun_variant_paradigms)
        if not paradigms or len(paradigms) <= 1:
            continue
        variant_records += 1

        artifact_forms = forms_from_artifacts(record, artifacts)
        if upos in ARTIFACT_WORD_CLASSES:
            generated_forms = artifact_forms or set()
        else:
            generated_forms = canonical_record_forms(record)

        direct = select_direct_match_from_artifacts(record, saldo, form_index, generated_forms)
        variant = select_article_variant_match_from_artifacts(
            record, saldo, form_index, generated_forms, paradigms
        )

        direct_method = direct[0] if direct else "no_match"
        variant_method = variant[0] if variant else "no_match"
        direct_analyses = direct[1] if direct else []
        variant_analyses = variant[1] if variant else []
        direct_status = _status(generated_forms, direct_analyses) if direct else "no_match"
        variant_status = _status(generated_forms, variant_analyses) if variant else "no_match"

        transition = f"{direct_status}->{variant_status}"
        method_transition = f"{direct_method}->{variant_method}"
        transition_counts[transition] += 1
        method_transition_counts[method_transition] += 1

        direct_ids = sorted({str(a.get("id") or "") for a in direct_analyses})
        variant_ids = sorted({str(a.get("id") or "") for a in variant_analyses})
        direct_lemmas = sorted({str(l) for a in direct_analyses for l in a.get("lemmas", ())}, key=str.casefold)
        variant_lemmas = sorted({str(l) for a in variant_analyses for l in a.get("lemmas", ())}, key=str.casefold)

        match_changed = (direct_method, direct_ids, direct_lemmas) != (variant_method, variant_ids, variant_lemmas)
        status_changed = direct_status != variant_status
        if match_changed:
            changed_match += 1
        if status_changed:
            changed_status += 1

        direct_mismatch = direct_status == "form_set_mismatch"
        variant_mismatch = variant_status == "form_set_mismatch"
        mismatch_delta += int(variant_mismatch) - int(direct_mismatch)

        if match_changed or status_changed:
            rows.append({
                "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
                "lemma": str(record.get("normaliserat_ord") or ""),
                "homonym_number": str(record.get("homonr") or ""),
                "notation": str(record.get("text") or ""),
                "variant_lemmas": list(paradigms),
                "direct_method": direct_method,
                "variant_method": variant_method,
                "direct_status": direct_status,
                "variant_status": variant_status,
                "direct_saldo_ids": direct_ids,
                "variant_saldo_ids": variant_ids,
                "direct_saldo_lemmas": direct_lemmas,
                "variant_saldo_lemmas": variant_lemmas,
                "generated_forms": sorted(generated_forms, key=str.casefold),
                "direct_saldo_forms": sorted(_analysis_forms(direct_analyses), key=str.casefold),
                "variant_saldo_forms": sorted(_analysis_forms(variant_analyses), key=str.casefold),
            })

    rows.sort(key=lambda row: (row["direct_status"] == row["variant_status"], row["lemma"].casefold(), row["record_id"]))
    summary = {
        "variant_records": variant_records,
        "changed_match_selection": changed_match,
        "changed_status": changed_status,
        "form_set_mismatch_delta": mismatch_delta,
        "status_transitions": dict(sorted(transition_counts.items())),
        "method_transitions": dict(sorted(method_transition_counts.items())),
        "detail_rows": len(rows),
    }
    return rows, summary


def render(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"Variantposter analyserade: {summary['variant_records']}",
        f"Ändrat SALDO-val: {summary['changed_match_selection']}",
        f"Ändrad status: {summary['changed_status']}",
        f"Nettoändring form_set_mismatch: {summary['form_set_mismatch_delta']:+d}",
        "",
        "Statusövergångar:",
    ]
    for transition, count in summary["status_transitions"].items():
        lines.append(f"  {count:5d}  {transition}")
    lines.extend(["", "Poster med ändrat val/status:"])
    for row in rows[:250]:
        lines.append(
            f"  {row['lemma']} ({row['homonym_number']}) record_id={row['record_id']} | "
            f"{row['direct_status']} -> {row['variant_status']} | "
            f"{row['direct_method']} -> {row['variant_method']}"
        )
        lines.append(f"    SAOL-varianter: {', '.join(row['variant_lemmas'])}")
        lines.append(f"    Direkt SALDO-lemma: {', '.join(row['direct_saldo_lemmas']) or '–'}")
        lines.append(f"    Variant SALDO-lemma: {', '.join(row['variant_saldo_lemmas']) or '–'}")
    lines.append("")
    return "\n".join(lines)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mät exakt effekt av artikelvariantmatchning mot SALDO")
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    rows, summary = analyze(args.saol, args.saldo_forms, args.noun_forms, args.adjective_forms)
    _write_jsonl(args.jsonl, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.write_text(render(summary, rows), encoding="utf-8")

    print(f"Variantposter analyserade: {summary['variant_records']}")
    print(f"Ändrat SALDO-val: {summary['changed_match_selection']}")
    print(f"Ändrad status: {summary['changed_status']}")
    print(f"Nettoändring form_set_mismatch: {summary['form_set_mismatch_delta']:+d}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
