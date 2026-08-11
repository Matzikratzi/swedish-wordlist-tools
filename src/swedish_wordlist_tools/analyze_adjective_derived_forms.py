from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .artifact_paths import SALDO_FORMS
from .generate_adjective_forms import DEFAULT_JSONL as DEFAULT_ADJECTIVE_FORMS
from .jsonl import read_jsonl
from .revalidate_direct_forms_core import select_direct_match_from_artifacts
from .saldo_form_artifact import build_form_index, read_saldo_forms
from .validate_direct_forms import _analysis_forms

DEFAULT_TEXT = Path("reports/saol14-adjective-derived-form-validation.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-derived-form-validation.json")

# Manual validation evidence is deliberately separate from generation rules.
# These forms were checked against the SAOL 2026 paradigm tables on svenska.se
# after SALDO failed to contain them.  The keys are evidence only; they never
# create or alter adjective forms.
_MANUAL_SAOL_CONFIRMATIONS: dict[tuple[str, str], str] = {
    ("ringa", "ringaste"): (
        "SAOL 2026: superlativ 'är ringast'; bestämd/plural 'den/det/de ringaste'"
    ),
    ("trång", "trängsta"): (
        "SAOL 2026: superlativ 'är trängst (trångast)'; "
        "bestämd/plural 'den/det/de trängsta (trångaste)'"
    ),
}


def _canonical_saldo_match(
    row: dict[str, Any],
    saldo: dict[str, list[dict[str, Any]]],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[set[str], tuple[str, ...], str, bool]:
    source_record = dict(row.get("source_record") or {})
    source_record["normaliserat_ord"] = str(row.get("lemma") or source_record.get("normaliserat_ord") or "")
    source_record["upos"] = "ADJ"
    generated_forms = {
        str(form.get("written_form") or "")
        for form in row.get("forms", ())
        if str(form.get("written_form") or "")
    }
    selected = select_direct_match_from_artifacts(
        source_record,
        saldo,
        form_index,
        generated_forms,
    )
    if selected is None:
        return set(), (), "", False
    method, analyses = selected
    forms = {form for analysis in analyses for form in _analysis_forms(analysis)}
    ids = tuple(sorted({str(analysis.get("id") or "") for analysis in analyses if analysis.get("id")}))
    return forms, ids, method, bool(analyses)


def build_rows(
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
    saldo_forms_path: Path = SALDO_FORMS,
) -> list[dict[str, Any]]:
    saldo = read_saldo_forms(saldo_forms_path)
    form_index = build_form_index(saldo)
    result: list[dict[str, Any]] = []

    for row in read_jsonl(adjective_forms_path):
        derived = [
            form
            for form in row.get("forms", ())
            if str(form.get("provenance") or "") == "derived_inflection"
        ]
        if not derived:
            continue

        lemma = str(row.get("lemma") or "")
        saldo_forms, saldo_ids, match_method, matched = _canonical_saldo_match(row, saldo, form_index)
        saldo_folded = {form.casefold() for form in saldo_forms}
        source_superlatives = sorted(
            {
                str(form.get("written_form") or "")
                for form in row.get("forms", ())
                if str(form.get("slot") or "") == "superlative"
            },
            key=str.casefold,
        )
        for form in derived:
            written_form = str(form.get("written_form") or "")
            manual_evidence = _MANUAL_SAOL_CONFIRMATIONS.get(
                (lemma.casefold(), written_form.casefold()), ""
            )
            if not matched:
                status = "lemma_missing_in_saldo"
            elif written_form.casefold() in saldo_folded:
                status = "confirmed_by_saldo"
            elif manual_evidence:
                status = "confirmed_by_saol_manual"
            else:
                status = "missing_from_saldo"
            result.append(
                {
                    "lemma": lemma,
                    "homonym_number": str(row.get("homonym_number") or ""),
                    "source_notation": str(row.get("source_notation") or ""),
                    "source_superlatives": source_superlatives,
                    "derived_form": written_form,
                    "derived_slot": str(form.get("slot") or ""),
                    "status": status,
                    "manual_saol_evidence": manual_evidence,
                    "saldo_match_method": match_method,
                    "saldo_ids": list(saldo_ids),
                    "saldo_forms": sorted(saldo_forms, key=str.casefold),
                }
            )

    result.sort(key=lambda item: (item["status"], item["lemma"].casefold(), item["derived_form"].casefold()))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["status"]) for row in rows)
    match_counts = Counter(str(row.get("saldo_match_method") or "") for row in rows if row.get("saldo_match_method"))
    verified = counts.get("confirmed_by_saldo", 0) + counts.get("confirmed_by_saol_manual", 0)
    return {
        "derived_forms": len(rows),
        "derived_lemmas": len({str(row["lemma"]).casefold() for row in rows}),
        "verified_forms": verified,
        "all_derived_forms_verified": verified == len(rows),
        "status_counts": dict(sorted(counts.items())),
        "match_method_counts": dict(sorted(match_counts.items())),
        "rows": rows,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 ADJ: härledda former validerade mot SALDO och SAOL",
        "",
        "SALDO används endast som extern kontroll. Reglerna härleds från SAOL,",
        "och avvikelse mot SALDO ändrar inte automatiskt den genererade formen.",
        "Manuella SAOL-bekräftelser är valideringsbevis och påverkar inte generatorn.",
        "Samma kanoniska lemma/UPOS-matchning används som i den ordinarie",
        "SAOL/SALDO-valideringen.",
        "",
        f"Härledda former: {summary['derived_forms']}",
        f"Lemma med härledda former: {summary['derived_lemmas']}",
        f"Verifierade former totalt: {summary['verified_forms']}/{summary['derived_forms']}",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"{status}: {count}")
    if summary.get("match_method_counts"):
        lines.append("")
        lines.append("SALDO-matchningsmetoder:")
        for method, count in summary["match_method_counts"].items():
            lines.append(f"  {count}  {method}")

    for status in (
        "missing_from_saldo",
        "lemma_missing_in_saldo",
        "confirmed_by_saol_manual",
        "confirmed_by_saldo",
    ):
        selected = [row for row in summary["rows"] if row["status"] == status]
        if not selected:
            continue
        lines.extend(("", f"{status}:"))
        for row in selected:
            base = ", ".join(row["source_superlatives"]) or "?"
            lines.append(
                f"  {row['lemma']} | {base} -> {row['derived_form']} | "
                f"slot={row['derived_slot']} | match={row.get('saldo_match_method') or '-'}"
            )
            if status in {"missing_from_saldo", "confirmed_by_saol_manual"}:
                lines.append("    SALDO: " + ", ".join(row["saldo_forms"]))
            if status == "confirmed_by_saol_manual":
                lines.append("    SAOL manual: " + str(row["manual_saol_evidence"]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validera endast härledda SAOL-adjektivformer mot SALDO och manuellt SAOL-bevis"
    )
    parser.add_argument("--adjectives", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--saldo", type=Path, default=SALDO_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = build_summary(build_rows(args.adjectives, args.saldo))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(summary), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Härledda former: {summary['derived_forms']}")
    print(f"Lemma med härledda former: {summary['derived_lemmas']}")
    print(f"Verifierade former totalt: {summary['verified_forms']}/{summary['derived_forms']}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    for method, count in summary["match_method_counts"].items():
        print(f"match {method}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
