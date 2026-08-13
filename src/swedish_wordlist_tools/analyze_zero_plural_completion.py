from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_JSON = Path("reports/saol14-zero-plural-completion.json")
DEFAULT_TEXT = Path("reports/saol14-zero-plural-completion.txt")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def analyze(
    validation_path: Path = DEFAULT_VALIDATION,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
) -> dict[str, Any]:
    noun_rows = {
        (str(row.get("record_id", "")), str(row.get("homonym_number", ""))): row
        for row in _read_jsonl(noun_forms_path)
    }
    selected: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()

    seen: set[tuple[str, str]] = set()
    for row in _read_jsonl(validation_path):
        if str(row.get("upos", "")).upper() != "NOUN":
            continue
        if str(row.get("notation", "")).strip() != "pl. +":
            continue
        if str(row.get("paradigm_status") or row.get("status", "")) != "form_set_mismatch":
            continue
        key = (str(row.get("record_id", "")), str(row.get("homonym_number", "")))
        if key in seen:
            continue
        seen.add(key)
        artifact = noun_rows.get(key)
        if artifact is None:
            # Some article-variant materializations collapse raw homonym rows.
            candidates = [
                candidate for (record_id, _homonym), candidate in noun_rows.items()
                if record_id == key[0]
            ]
            artifact = candidates[0] if candidates else None

        forms = list((artifact or {}).get("forms", []))
        for form in forms:
            kind_counts[str(form.get("kind", ""))] += 1
            stage_counts[str(form.get("source_stage", ""))] += 1

        selected.append(
            {
                "lemma": str(row.get("lemma", "")),
                "record_id": key[0],
                "homonym_number": key[1],
                "generated_forms": list(row.get("generated_forms", [])),
                "saldo_forms": list(row.get("saldo_forms", [])),
                "extra_from_saol": list(row.get("extra_from_saol", [])),
                "missing_from_saol": list(row.get("missing_from_saol", [])),
                "artifact_forms": forms,
            }
        )

    selected.sort(key=lambda item: item["lemma"].casefold())
    derived_definite_rows = 0
    for row in selected:
        if any(form.get("kind") == "derived_definite_plural" for form in row["artifact_forms"]):
            derived_definite_rows += 1

    return {
        "records": len(selected),
        "rows_with_derived_definite_plural": derived_definite_rows,
        "form_kind_counts": dict(sorted(kind_counts.items())),
        "source_stage_counts": dict(sorted(stage_counts.items())),
        "rows": selected,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 audit: notation pl. + och noun completion",
        "",
        f"Poster: {summary['records']}",
        f"Poster med derived_definite_plural: {summary['rows_with_derived_definite_plural']}",
        "Form kinds: " + ", ".join(f"{k}={v}" for k, v in summary["form_kind_counts"].items()),
        "Source stages: " + ", ".join(f"{k}={v}" for k, v in summary["source_stage_counts"].items()),
    ]
    for row in summary["rows"]:
        lines.extend(["", "=" * 72, f"{row['lemma']}  record_id={row['record_id']} homonr={row['homonym_number']}"])
        lines.append("Extra SAOL: " + (", ".join(row["extra_from_saol"]) or "–"))
        lines.append("Saknas SAOL: " + (", ".join(row["missing_from_saol"]) or "–"))
        lines.append("Artefaktformer:")
        for form in row["artifact_forms"]:
            lines.append(
                "  {written_form}  msd={msd} kind={kind} stage={source_stage}".format(
                    written_form=form.get("written_form", ""),
                    msd=form.get("msd", ""),
                    kind=form.get("kind", ""),
                    source_stage=form.get("source_stage", ""),
                )
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SAOL14 pl. + completion semantics")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = analyze(args.validation, args.noun_forms)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.write_text(render_text(summary), encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print(f"Poster med derived_definite_plural: {summary['rows_with_derived_definite_plural']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
