from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .generate_noun_forms import canonical_noun_row
from .jsonl import read_jsonl
from .materialize_saol_relations import DEFAULT_ARTICLES, DEFAULT_HEADINGS
from .noun_article_variants import NounArticleVariantPlan, plan_noun_article_variants
from .noun_paradigm import complete_noun_entry
from .noun_relational_source import reconstruct_source_rows, relational_integrity_summary

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
# This command is the canonical noun-artifact writer. If the artifact already
# exists, it is read first as the baseline so the impact report remains useful.
DEFAULT_BASELINE = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_JSONL = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-forms-grouped-impact.txt")
DEFAULT_SUMMARY = Path("reports/saol14-noun-forms-grouped-summary.json")
DEFAULT_RELATIONAL_AUDIT = Path("reports/saol14-noun-relational-source-audit.txt")
DEFAULT_RELATIONAL_AUDIT_JSON = Path("reports/saol14-noun-relational-source-audit.json")


def record_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("subnr") or row.get("urspr_lopnr") or "")


def article_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("urspr_lopnr") or row.get("subnr") or row.get("id") or ""),
        str(row.get("subnr") or row.get("urspr_lopnr") or row.get("id") or ""),
    )


def _form_dict(form: Any) -> dict[str, Any]:
    return {
        "written_form": form.written_form,
        "msd": str(form.msd) if form.msd is not None else None,
        "kind": form.kind,
        "source_stage": "noun_interpreter" if form.kind in {"lemma", "interpreted_slot"} else "noun_completion",
    }


def _primary_source_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose the display/provenance row for one materialized SAOL article."""

    return next((row for row in rows if str(row.get("homonr") or "") == "1"), rows[0])


def _article_variant_row(
    source_rows: list[dict[str, Any]],
    plan: NounArticleVariantPlan,
) -> dict[str, Any] | None:
    source_row = _primary_source_row(source_rows)
    merged: list[Any] = []
    seen: set[tuple[str, str | None]] = set()
    paradigms: list[dict[str, Any]] = []

    for variant in plan.variants:
        synthetic = dict(source_row)
        synthetic["normaliserat_ord"] = variant.lemma
        synthetic["ord"] = variant.lemma
        synthetic["stycke"] = variant.lemma
        synthetic["text"] = variant.notation
        entry = complete_noun_entry(synthetic, None)
        if entry is None:
            return None

        variant_forms = [_form_dict(form) for form in entry.word_forms]
        paradigms.append(
            {
                "lemma": variant.lemma,
                "notation": variant.notation,
                "forms": variant_forms,
            }
        )
        for form in entry.word_forms:
            marker = (form.written_form, str(form.msd) if form.msd is not None else None)
            if marker not in seen:
                seen.add(marker)
                merged.append(form)

    homonyms = sorted(
        {str(row.get("homonr") or "") for row in source_rows if str(row.get("homonr") or "")},
        key=lambda value: (value != "1", value),
    )
    return {
        "article_id": record_id(source_row),
        "completion_applied": True,
        # Compatibility union. variant_paradigms is the primary structure.
        "forms": [_form_dict(form) for form in merged],
        "homonym_number": "1" if "1" in homonyms else (homonyms[0] if homonyms else ""),
        "source_homonym_numbers": homonyms,
        "lemma": str(source_row.get("normaliserat_ord") or ""),
        "notation": str(source_row.get("text") or ""),
        "ordkl": str(source_row.get("ordkl") or ""),
        "pattern": str(source_row.get("text") or ""),
        "pattern_group": "article variant paradigms",
        "record_id": record_id(source_row),
        "source": str(source_row.get("source") or ""),
        "stycke": str(source_row.get("stycke") or ""),
        "upos": "NOUN",
        "variant_mode": plan.mode,
        "variant_lemmas": [variant.lemma for variant in plan.variants],
        "variant_paradigms": paradigms,
    }


def generate_grouped(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nouns = [row for row in records if _saol_upos(row) == "NOUN"]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        groups[article_key(row)].append(row)

    output: list[dict[str, Any]] = []
    variant_groups = 0
    variant_source_rows = 0
    variant_artifact_rows = 0
    mode_counts: Counter[str] = Counter()
    unresolved_multiline_groups = 0

    for rows in groups.values():
        plan = plan_noun_article_variants(rows)
        if plan is not None:
            variant_groups += 1
            mode_counts[plan.mode] += 1
            row = _article_variant_row(rows, plan)
            if row is not None:
                output.append(row)
                variant_source_rows += len(rows)
                variant_artifact_rows += 1
                continue
        elif len(rows) > 1:
            unresolved_multiline_groups += 1

        # Unresolved/non-variant groups keep the established row-local path.
        for source_row in rows:
            row, _comparison = canonical_noun_row(source_row)
            if row is not None:
                output.append(row)

    output.sort(key=lambda row: (str(row["lemma"]).casefold(), str(row["homonym_number"]), str(row["record_id"])))
    summary = {
        "noun_rows": len(nouns),
        "article_groups": len(groups),
        "generated_rows": len(output),
        "variant_groups": variant_groups,
        "variant_source_rows": variant_source_rows,
        "variant_artifact_rows": variant_artifact_rows,
        "variant_mode_counts": dict(sorted(mode_counts.items())),
        "unresolved_multiline_groups": unresolved_multiline_groups,
        # Backwards-compatible names used by older reports/tests.
        "variant_rows": variant_source_rows,
        "proven_variant_groups": variant_groups,
        "proven_variant_rows": variant_source_rows,
        "canonical_form_rows": sum(len(row["forms"]) for row in output),
        "canonical_unique_written_forms": len({str(form["written_form"]).casefold() for row in output for form in row["forms"]}),
        "artifact": str(DEFAULT_JSONL),
        "scope": "structurally unambiguous SAOL article variants",
    }
    return output, summary


def _form_sets(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
    """Compare baselines by article id + lemma, independent of duplicated homonr rows."""

    result: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        key = (str(row.get("record_id") or ""), str(row.get("lemma") or ""))
        result.setdefault(key, set()).update(
            str(form.get("written_form") or "")
            for form in row.get("forms", [])
            if form.get("written_form")
        )
    return result


def compare_to_baseline(new_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    new = _form_sets(new_rows)
    old = _form_sets(baseline_rows)
    impact: list[dict[str, Any]] = []
    for key in sorted(set(new) | set(old), key=lambda x: (x[1].casefold(), x[0])):
        before = old.get(key, set())
        after = new.get(key, set())
        if before == after:
            continue
        impact.append({
            "record_id": key[0],
            "lemma": key[1],
            "added": sorted(after - before, key=str.casefold),
            "removed": sorted(before - after, key=str.casefold),
        })
    return impact


def render_impact(summary: dict[str, Any], impact: list[dict[str, Any]]) -> str:
    added = Counter(form for row in impact for form in row["added"])
    removed = Counter(form for row in impact for form in row["removed"])
    lines = [
        f"Omfattning: {summary['scope']}",
        f"Artikelgrupper: {summary['article_groups']}",
        f"Entydiga variantgrupper: {summary['variant_groups']}",
        f"Variantlägen: {summary['variant_mode_counts']}",
        f"Flerradsgrupper ej automatiskt lösta: {summary['unresolved_multiline_groups']}",
        f"Rå-rader som ingår i variantartiklar: {summary['variant_source_rows']}",
        f"Materialiserade variantartiklar: {summary['variant_artifact_rows']}",
        f"Poster med ändrad formmängd mot baseline: {len(impact)}",
        f"Unika tillagda former: {len(added)}",
        f"Unika borttagna former: {len(removed)}",
        "",
        "Ändrade artiklar:",
    ]
    for row in impact:
        lines.append(f"  {row['lemma']} (record_id={row['record_id']})")
        lines.append("    + " + (", ".join(row["added"]) or "–"))
        lines.append("    - " + (", ".join(row["removed"]) or "–"))
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def exact_artifact_differences(
    relational_rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    missing = object()
    for index, (relational, raw) in enumerate(zip_longest(relational_rows, raw_rows, fillvalue=missing)):
        if relational == raw:
            continue
        differences.append({
            "index": index,
            "relational": None if relational is missing else {
                "record_id": str(relational.get("record_id") or ""),
                "lemma": str(relational.get("lemma") or ""),
                "homonym_number": str(relational.get("homonym_number") or ""),
            },
            "raw": None if raw is missing else {
                "record_id": str(raw.get("record_id") or ""),
                "lemma": str(raw.get("lemma") or ""),
                "homonym_number": str(raw.get("homonym_number") or ""),
            },
        })
        if len(differences) >= limit:
            break
    return differences


def render_relational_audit(audit: dict[str, Any]) -> str:
    lines = [
        f"Källa: {audit['source_mode']}",
        f"Relationsartiklar: {audit['integrity']['articles']}",
        f"Relationsrubriker: {audit['integrity']['headings']}",
        f"Rubriker utan artikel: {audit['integrity']['dangling_headings']}",
        f"Artiklar utan rubrik: {audit['integrity']['articles_without_headings']}",
        f"Rekonstruerade källrader: {audit['reconstructed_source_rows']}",
        f"Exakt lika mot råvägen: {'JA' if audit['exact_raw_equivalence'] else 'NEJ'}",
        f"Relationsgenererade artefaktrader: {audit['relational_artifact_rows']}",
        f"Rågenererade artefaktrader: {audit['raw_artifact_rows']}",
        "",
    ]
    if audit["differences"]:
        lines.append("Första skillnaderna:")
        for item in audit["differences"]:
            lines.append(f"  index={item['index']} relational={item['relational']} raw={item['raw']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate canonical SAOL noun forms from the materialized article model"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL, help="raw SAOL used only for equivalence checking or --source-mode raw")
    parser.add_argument("--source-mode", choices=("relational", "raw"), default="relational")
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES)
    parser.add_argument("--headings", type=Path, default=DEFAULT_HEADINGS)
    parser.add_argument("--skip-raw-equivalence-check", action="store_true")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--relational-audit", type=Path, default=DEFAULT_RELATIONAL_AUDIT)
    parser.add_argument("--relational-audit-json", type=Path, default=DEFAULT_RELATIONAL_AUDIT_JSON)
    args = parser.parse_args()

    baseline_rows = list(read_jsonl(args.baseline)) if args.baseline.exists() else []

    if args.source_mode == "raw":
        rows, summary = generate_grouped(read_jsonl(args.saol))
        audit = {
            "source_mode": "raw",
            "integrity": {"articles": 0, "headings": 0, "dangling_headings": 0, "articles_without_headings": 0},
            "reconstructed_source_rows": 0,
            "exact_raw_equivalence": True,
            "relational_artifact_rows": len(rows),
            "raw_artifact_rows": len(rows),
            "differences": [],
        }
    else:
        if not args.articles.exists() or not args.headings.exists():
            raise SystemExit(
                "Relationsartefakterna saknas. Kör först: python -m swedish_wordlist_tools.materialize_saol_relations"
            )
        articles = list(read_jsonl(args.articles))
        headings = list(read_jsonl(args.headings))
        integrity = relational_integrity_summary(articles, headings)
        if integrity["dangling_headings"] or integrity["articles_without_headings"]:
            raise SystemExit(f"Relationsmodellen är inte komplett: {integrity}")
        reconstructed = reconstruct_source_rows(articles, headings)
        rows, summary = generate_grouped(reconstructed)

        raw_generated: list[dict[str, Any]] = []
        differences: list[dict[str, Any]] = []
        exact = True
        if not args.skip_raw_equivalence_check:
            raw_generated, _raw_summary = generate_grouped(read_jsonl(args.saol))
            differences = exact_artifact_differences(rows, raw_generated)
            exact = rows == raw_generated
        audit = {
            "source_mode": "relational",
            "integrity": integrity,
            "reconstructed_source_rows": len(reconstructed),
            "exact_raw_equivalence": exact,
            "relational_artifact_rows": len(rows),
            "raw_artifact_rows": len(raw_generated) if not args.skip_raw_equivalence_check else None,
            "differences": differences,
        }
        args.relational_audit.parent.mkdir(parents=True, exist_ok=True)
        args.relational_audit.write_text(render_relational_audit(audit), encoding="utf-8")
        args.relational_audit_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not exact:
            raise SystemExit(
                f"Relationsvägen skiljer sig från råvägen. Officiell noun-artefakt skrevs INTE. Se {args.relational_audit}"
            )

    impact = compare_to_baseline(rows, baseline_rows) if baseline_rows else []
    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_impact(summary, impact), encoding="utf-8")
    summary = dict(
        summary,
        changed_against_baseline=len(impact),
        artifact=str(args.jsonl),
        source_mode=args.source_mode,
        exact_raw_equivalence=audit["exact_raw_equivalence"],
    )
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Källa för noun-generatorn: {args.source_mode}")
    if args.source_mode == "relational":
        print(f"Exakt lika mot gamla råvägen: {'JA' if audit['exact_raw_equivalence'] else 'NEJ'}")
        print(f"Relationsaudit: {args.relational_audit}")
    print(f"Entydiga variantgrupper: {summary['variant_groups']}")
    print(f"Variantlägen: {summary['variant_mode_counts']}")
    print(f"Flerradsgrupper ej automatiskt lösta: {summary['unresolved_multiline_groups']}")
    print(f"Rå-rader i variantartiklar: {summary['variant_source_rows']}")
    print(f"Materialiserade variantartiklar: {summary['variant_artifact_rows']}")
    print(f"Ändrade mot baseline: {summary['changed_against_baseline']}")
    print(f"Officiell noun-artefakt: {args.jsonl}")
    print(f"Impact: {args.text}")


if __name__ == "__main__":
    main()
