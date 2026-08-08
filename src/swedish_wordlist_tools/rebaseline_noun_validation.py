from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyze_singular_agreement_for_scope_extras import candidates as scope_candidates
from .triage_singular_scope_mismatches import classify as classify_scope_mismatch

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-validation-rebaseline.txt")
DEFAULT_JSON = Path("reports/saol14-noun-validation-rebaseline.json")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def classify(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nouns = [row for row in rows if str(row.get("upos") or "").upper() == "NOUN"]
    scope = scope_candidates(nouns)
    by_key = {
        (row["record_id"], row["homonym_number"], row["lemma"]): row
        for row in scope
    }
    mismatches = [row for row in scope if row["singular_status"] == "singular_mismatch"]
    triage_by_key: dict[tuple[str, str, str], str] = {}
    for row in mismatches:
        category, _rationale = classify_scope_mismatch(row)
        triage_by_key[(row["record_id"], row["homonym_number"], row["lemma"])] = category

    counts = Counter()
    examples: dict[str, list[str]] = {}

    def add(bucket: str, lemma: str) -> None:
        counts[bucket] += 1
        examples.setdefault(bucket, [])
        if len(examples[bucket]) < 20:
            examples[bucket].append(lemma)

    for row in nouns:
        key = (
            str(row.get("record_id") or ""),
            str(row.get("homonym_number") or ""),
            str(row.get("lemma") or ""),
        )
        scoped = by_key.get(key)
        if scoped is not None:
            if scoped["singular_status"] == "singular_exact":
                add("scope_extra_singular_verified", scoped["lemma"])
                continue
            category = triage_by_key.get(key)
            if category is not None:
                add("scope_mismatch_" + category, scoped["lemma"])
                continue

        status = str(row.get("status") or "")
        if status == "exact_form_set":
            add("exact_form_set", str(row.get("lemma") or ""))
        elif status == "exact_form_set_case_difference":
            add("exact_form_set_case_difference", str(row.get("lemma") or ""))
        elif status == "saol_forms_are_subset":
            add("other_saol_subset", str(row.get("lemma") or ""))
        elif status == "saol_pattern_unsupported":
            add("unsupported", str(row.get("lemma") or ""))
        elif status == "form_set_mismatch":
            add("remaining_form_set_mismatch", str(row.get("lemma") or ""))
        else:
            add("other_status", str(row.get("lemma") or ""))

    return {
        "noun_records": len(nouns),
        "counts": dict(counts.most_common()),
        "examples": examples,
        "scope_population": len(scope),
        "scope_singular_exact": sum(1 for row in scope if row["singular_status"] == "singular_exact"),
        "scope_singular_mismatch": len(mismatches),
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: ny valideringsbaslinje",
        "",
        "Princip: SAOL-artikelns egna slots är auktoritativa. SALDO används som jämförelsekälla.",
        "Singular-only-artiklar där hela SAOL-singularet finns i SALDO räknas som starkt verifierade",
        "även om SALDO dessutom innehåller plural utanför artikelomfånget.",
        "",
        f"NOUN-poster: {summary['noun_records']}",
        f"Artikelomfångspopulation: {summary['scope_population']}",
        f"  singular exakt: {summary['scope_singular_exact']}",
        f"  singular mismatch: {summary['scope_singular_mismatch']}",
        "",
        "Ny toppnivåfördelning:",
    ]
    for name, count in summary["counts"].items():
        lines.append(f"{count:6}  {name}")
    lines.append("")
    lines.append("Exempel:")
    for name, items in summary["examples"].items():
        lines.append(f"  {name}: {', '.join(items)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = classify(read_jsonl(args.input))
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
