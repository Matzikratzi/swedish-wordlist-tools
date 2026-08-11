from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .artifact_paths import SALDO_FORMS
from .compare_sources import _key
from .generate_adjective_forms import DEFAULT_JSONL as DEFAULT_ADJECTIVE_FORMS
from .jsonl import read_jsonl
from .saldo_form_artifact import read_saldo_forms

DEFAULT_TEXT = Path("reports/saol14-adjective-derived-form-validation.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-derived-form-validation.json")


def _saldo_adjective_forms(
    lemma: str,
    saldo: dict[str, list[dict[str, Any]]],
) -> tuple[set[str], tuple[str, ...]]:
    analyses = [
        analysis
        for analysis in saldo.get(_key(lemma), ())
        if str(analysis.get("upos") or "").upper() == "ADJ"
    ]
    forms = {str(form) for analysis in analyses for form in analysis.get("forms", ())}
    ids = tuple(sorted({str(analysis.get("id") or "") for analysis in analyses if analysis.get("id")}))
    return forms, ids


def build_rows(
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
    saldo_forms_path: Path = SALDO_FORMS,
) -> list[dict[str, Any]]:
    saldo = read_saldo_forms(saldo_forms_path)
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
        saldo_forms, saldo_ids = _saldo_adjective_forms(lemma, saldo)
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
            if not saldo_ids:
                status = "lemma_missing_in_saldo"
            elif written_form.casefold() in saldo_folded:
                status = "confirmed_by_saldo"
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
                    "saldo_ids": list(saldo_ids),
                    "saldo_forms": sorted(saldo_forms, key=str.casefold),
                }
            )

    result.sort(key=lambda item: (item["status"], item["lemma"].casefold(), item["derived_form"].casefold()))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["status"]) for row in rows)
    return {
        "derived_forms": len(rows),
        "derived_lemmas": len({str(row["lemma"]).casefold() for row in rows}),
        "status_counts": dict(sorted(counts.items())),
        "rows": rows,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 ADJ: härledda former validerade mot SALDO",
        "",
        "SALDO används endast som extern kontroll. Reglerna härleds från SAOL,",
        "och avvikelse mot SALDO ändrar inte automatiskt den genererade formen.",
        "",
        f"Härledda former: {summary['derived_forms']}",
        f"Lemma med härledda former: {summary['derived_lemmas']}",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"{status}: {count}")

    for status in ("missing_from_saldo", "lemma_missing_in_saldo", "confirmed_by_saldo"):
        selected = [row for row in summary["rows"] if row["status"] == status]
        if not selected:
            continue
        lines.extend(("", f"{status}:"))
        for row in selected:
            base = ", ".join(row["source_superlatives"]) or "?"
            lines.append(
                f"  {row['lemma']} | {base} -> {row['derived_form']} | "
                f"slot={row['derived_slot']}"
            )
            if status == "missing_from_saldo":
                lines.append("    SALDO: " + ", ".join(row["saldo_forms"]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validera endast härledda SAOL-adjektivformer mot SALDO"
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
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
