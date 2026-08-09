from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyze_singular_agreement_for_scope_extras import candidates as scope_candidates
from .noun_mechanical_validation import is_mechanically_verified_noun_row
from .saol_source_policy import is_truncated_inflection_source
from .triage_singular_scope_mismatches import classify as classify_scope_mismatch

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_HOMONYM_COVERAGE = Path("reports/saol14-unequal-homonym-paradigm-coverage.json")
DEFAULT_TEXT = Path("reports/saol14-noun-validation-rebaseline.txt")
DEFAULT_JSON = Path("reports/saol14-noun-validation-rebaseline.json")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def homonym_coverage_diagnostics(summary: dict[str, Any] | None) -> dict[str, int]:
    if not summary:
        counts: dict[str, int] = {}
        lemmas = 0
    else:
        counts = {str(k): int(v) for k, v in summary.get("status_counts", {}).items()}
        if not counts:
            counter = Counter(str(row.get("status") or "") for row in summary.get("rows", ()))
            counts = {key: value for key, value in counter.items() if key}
        lemmas = int(summary.get("lemmas", len(summary.get("rows", ()))))
    exact = int(counts.get("at_least_one_saol_homonym_exactly_verified", 0))
    subset = int(counts.get("at_least_one_saol_homonym_subset_verified", 0))
    none = int(counts.get("no_saol_homonym_verified", 0))
    return {
        "at_least_one_saol_homonym_exactly_verified": exact,
        "at_least_one_saol_homonym_subset_verified": subset,
        "no_saol_homonym_verified": none,
        "lemmas": lemmas,
        "exact_sibling": exact,
        "subset_sibling": subset,
        "none_verified": none,
    }


def classify(rows: list[dict[str, Any]], homonym_coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    nouns = [row for row in rows if str(row.get("upos") or "").upper() == "NOUN"]
    scope = scope_candidates(nouns)
    by_key = {(row["record_id"], row["homonym_number"], row["lemma"]): row for row in scope}
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
        lemma = str(row.get("lemma") or "")
        status = str(row.get("status") or "")

        # A 50-character SAOL text field is known to be source-truncated. Keep
        # it out of every ordinary mismatch/triage queue even when the safe
        # prefix was sufficient to generate some forms. The missing tail is a
        # source-data problem, not a parser problem.
        if status == "form_set_mismatch" and is_truncated_inflection_source(row):
            add("source_text_truncated", lemma)
            continue

        key = (str(row.get("record_id") or ""), str(row.get("homonym_number") or ""), lemma)
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
        elif status == "form_set_mismatch" and is_mechanically_verified_noun_row(row):
            add("mechanically_verified_from_saol", lemma)
        elif status == "form_set_mismatch":
            add("remaining_form_set_mismatch", lemma)
        else:
            add("other_status", lemma)

    homonym_diag = homonym_coverage_diagnostics(homonym_coverage)
    return {
        "noun_records": len(nouns),
        "counts": dict(counts.most_common()),
        "examples": examples,
        "scope_population": len(scope),
        "scope_singular_exact": sum(1 for row in scope if row["singular_status"] == "singular_exact"),
        "scope_singular_mismatch": len(mismatches),
        "homonym_diagnostics": homonym_diag,
        "unequal_homonym_coverage": homonym_diag,
    }


def render(summary: dict[str, Any]) -> str:
    hom = summary["homonym_diagnostics"]
    lines = [
        "SAOL14 NOUN: ny valideringsbaslinje",
        "",
        "Princip: SAOL-artikelns egna slots är auktoritativa. SALDO används som jämförelsekälla.",
        "Enkla, granskade standardparadigm räknas som mekaniskt verifierade från SAOL+SAG;",
        "SALDO-avvikelser för dessa är diagnostik och håller inte kvar posten i konfliktkön.",
        "50-teckenstrunkerade text-fält ligger separat som source_text_truncated och",
        "räknas inte som vanliga parser-/formmismatchar.",
        "",
        f"NOUN-poster: {summary['noun_records']}",
        f"Artikelomfångspopulation: {summary['scope_population']}",
        f"  singular exakt: {summary['scope_singular_exact']}",
        f"  singular mismatch: {summary['scope_singular_mismatch']}",
        "",
        "Homonymdiagnostik när SAOL/SALDO har olika antal analyser:",
        f"  lemma: {hom['lemmas']}",
        f"  minst en exakt verifierad systerhomonym: {hom['exact_sibling']}",
        f"  minst en subset-verifierad systerhomonym: {hom['subset_sibling']}",
        f"  ingen SAOL-homonym verifierad: {hom['none_verified']}",
        "  Obs: verifierad systerhomonym omklassar inte den avvikande homonymen.",
        "",
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
