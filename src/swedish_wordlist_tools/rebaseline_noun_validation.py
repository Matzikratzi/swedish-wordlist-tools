from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyze_singular_agreement_for_scope_extras import candidates as scope_candidates
from .triage_singular_scope_mismatches import classify as classify_scope_mismatch

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_HOMONYM_COVERAGE = Path("reports/saol14-unequal-homonym-paradigm-coverage.json")
DEFAULT_TEXT = Path("reports/saol14-noun-validation-rebaseline.txt")
DEFAULT_JSON = Path("reports/saol14-noun-validation-rebaseline.json")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _lemma_key(value: object) -> str:
    return str(value or "").strip().casefold()


def _form_signature(values: object) -> tuple[str, ...]:
    return tuple(sorted({str(v).casefold() for v in (values or ()) if str(v)}))


def homonym_coverage_indexes(summary: dict[str, Any] | None) -> tuple[
    dict[str, str],
    dict[tuple[str, str], str],
    dict[tuple[str, tuple[str, ...]], str],
]:
    by_record: dict[str, str] = {}
    by_homonym: dict[tuple[str, str], str] = {}
    by_forms: dict[tuple[str, tuple[str, ...]], str] = {}
    if not summary:
        return by_record, by_homonym, by_forms
    for row in summary.get("rows", ()):
        lemma = _lemma_key(row.get("lemma"))
        exact = {str(value) for value in row.get("exact_saol_homonyms", ())}
        subset = {str(value) for value in row.get("subset_saol_homonyms", ())}
        for record_id in row.get("exact_saol_record_ids", ()):
            if str(record_id):
                by_record[str(record_id)] = "homonym_exact_verified"
        for record_id in row.get("subset_saol_record_ids", ()):
            rid = str(record_id)
            if rid and rid not in by_record:
                by_record[rid] = "homonym_subset_verified"
        for homonym in exact:
            by_homonym[(lemma, homonym)] = "homonym_exact_verified"
        for homonym in subset - exact:
            by_homonym[(lemma, homonym)] = "homonym_subset_verified"
        exact_form_keys = {_form_signature(forms) for forms in row.get("exact_saol_form_signatures", ())}
        for forms in row.get("exact_saol_form_signatures", ()):
            by_forms[(lemma, _form_signature(forms))] = "homonym_exact_verified"
        for forms in row.get("subset_saol_form_signatures", ()):
            sig = _form_signature(forms)
            if sig not in exact_form_keys:
                by_forms[(lemma, sig)] = "homonym_subset_verified"
    return by_record, by_homonym, by_forms


def classify(rows: list[dict[str, Any]], homonym_coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    nouns = [row for row in rows if str(row.get("upos") or "").upper() == "NOUN"]
    scope = scope_candidates(nouns)
    by_key = {(row["record_id"], row["homonym_number"], row["lemma"]): row for row in scope}
    mismatches = [row for row in scope if row["singular_status"] == "singular_mismatch"]
    triage_by_key: dict[tuple[str, str, str], str] = {}
    for row in mismatches:
        category, _rationale = classify_scope_mismatch(row)
        triage_by_key[(row["record_id"], row["homonym_number"], row["lemma"])] = category

    homonym_by_record, homonym_by_key, homonym_by_forms = homonym_coverage_indexes(homonym_coverage)
    counts = Counter()
    examples: dict[str, list[str]] = {}

    def add(bucket: str, lemma: str) -> None:
        counts[bucket] += 1
        examples.setdefault(bucket, [])
        if len(examples[bucket]) < 20:
            examples[bucket].append(lemma)

    for row in nouns:
        lemma = str(row.get("lemma") or "")
        lemma_key = _lemma_key(lemma)
        homonym = str(row.get("homonym_number") or "")
        record_id = str(row.get("record_id") or "")
        status = str(row.get("status") or "")

        homonym_status = homonym_by_record.get(record_id)
        if homonym_status is None:
            homonym_status = homonym_by_key.get((lemma_key, homonym))
        if homonym_status is None:
            homonym_status = homonym_by_forms.get((lemma_key, _form_signature(row.get("generated_forms"))))
        if homonym_status is not None and status == "form_set_mismatch":
            add(homonym_status, lemma)
            continue

        key = (record_id, homonym, lemma)
        scoped = by_key.get(key)
        if scoped is not None:
            if scoped["singular_status"] == "singular_exact":
                add("scope_extra_singular_verified", scoped["lemma"])
                continue
            category = triage_by_key.get(key)
            if category is not None:
                add("scope_mismatch_" + category, scoped["lemma"])
                continue

        if status == "exact_form_set":
            add("exact_form_set", lemma)
        elif status == "exact_form_set_case_difference":
            add("exact_form_set_case_difference", lemma)
        elif status == "saol_forms_are_subset":
            add("other_saol_subset", lemma)
        elif status == "saol_pattern_unsupported":
            add("unsupported", lemma)
        elif status == "form_set_mismatch":
            add("remaining_form_set_mismatch", lemma)
        else:
            add("other_status", lemma)

    return {
        "noun_records": len(nouns),
        "counts": dict(counts.most_common()),
        "examples": examples,
        "scope_population": len(scope),
        "scope_singular_exact": sum(1 for row in scope if row["singular_status"] == "singular_exact"),
        "scope_singular_mismatch": len(mismatches),
        "homonym_coverage_records": sum(count for name, count in counts.items() if name in {"homonym_exact_verified", "homonym_subset_verified"}),
        "homonym_coverage_record_count": len(homonym_by_record),
        "homonym_coverage_key_count": len(homonym_by_key),
        "homonym_coverage_signature_count": len(homonym_by_forms),
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: ny valideringsbaslinje", "",
        "Princip: SAOL-artikelns egna slots är auktoritativa. SALDO används som jämförelsekälla.",
        "Singular-only-artiklar där hela SAOL-singularet finns i SALDO räknas som starkt verifierade",
        "även om SALDO dessutom innehåller plural utanför artikelomfånget.",
        "För lemma med olika antal SAOL-/SALDO-homonymer räknas varje SAOL-homonym separat:",
        "endast den homonym vars eget paradigm är exakt verifierat eller subset-verifierat flyttas ur konfliktkön.", "",
        f"NOUN-poster: {summary['noun_records']}",
        f"Artikelomfångspopulation: {summary['scope_population']}",
        f"  singular exakt: {summary['scope_singular_exact']}",
        f"  singular mismatch: {summary['scope_singular_mismatch']}",
        f"Homonymposter verifierade trots olika analysantal: {summary['homonym_coverage_records']}",
        f"Coverage-nycklar: record_id={summary['homonym_coverage_record_count']}, homonym={summary['homonym_coverage_key_count']}, formsignatur={summary['homonym_coverage_signature_count']}", "",
        "Ny toppnivåfördelning:",
    ]
    for name, count in summary["counts"].items():
        lines.append(f"{count:6}  {name}")
    lines.extend(["", "Exempel:"])
    for name, items in summary["examples"].items():
        lines.append(f"  {name}: {', '.join(items)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--homonym-coverage", type=Path, default=DEFAULT_HOMONYM_COVERAGE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    homonym_coverage = json.loads(args.homonym_coverage.read_text(encoding="utf-8")) if args.homonym_coverage.exists() else None
    summary = classify(read_jsonl(args.input), homonym_coverage=homonym_coverage)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NOUN-poster: {summary['noun_records']}")
    for name, count in summary["counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
