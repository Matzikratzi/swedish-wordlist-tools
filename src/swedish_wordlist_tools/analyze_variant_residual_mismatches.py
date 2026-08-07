from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_noun_variant_mismatch_delta import analyze as analyze_delta
from .canonical_form_artifacts import DEFAULT_ADJECTIVE_FORMS, DEFAULT_NOUN_FORMS
from .jsonl import read_jsonl
from .saldo_form_artifact import DEFAULT_SALDO_FORMS
from .validate_direct_forms import DEFAULT_SAOL

DEFAULT_TEXT = Path("reports/saol14-variant-residual-mismatches.txt")
DEFAULT_JSONL = Path("reports/saol14-variant-residual-mismatches.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-variant-residual-mismatches-summary.json")


def _artifact_index(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[(str(row.get("record_id") or ""), str(row.get("lemma") or ""))].append(row)
    return result


def _source_details(form: dict[str, Any]) -> list[dict[str, str]]:
    sources = form.get("variant_sources")
    if isinstance(sources, list) and sources:
        return [
            {
                "heading": str(item.get("heading") or ""),
                "variant_lemma": str(item.get("variant_lemma") or ""),
                "variant_source": str(item.get("variant_source") or ""),
            }
            for item in sources
        ]
    return [
        {
            "heading": str(form.get("heading") or ""),
            "variant_lemma": str(form.get("variant_lemma") or ""),
            "variant_source": str(form.get("variant_source") or "unknown"),
        }
    ]


def _extra_form_provenance(
    artifact: dict[str, Any] | None,
    extra_forms: set[str],
) -> dict[str, list[dict[str, str]]]:
    if artifact is None:
        return {form: [] for form in sorted(extra_forms, key=str.casefold)}
    result: dict[str, list[dict[str, str]]] = {}
    for form in artifact.get("forms", []):
        written = str(form.get("written_form") or "")
        if written in extra_forms:
            result[written] = _source_details(form)
    for written in extra_forms:
        result.setdefault(written, [])
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def _reason(
    *,
    match_method: str,
    extra_provenance: dict[str, list[dict[str, str]]],
    missing_forms: set[str],
) -> str:
    if match_method == "article_variant_lemmas_same_upos_partial":
        return "partial_variant_saldo_coverage"

    source_kinds = {
        source.get("variant_source", "")
        for sources in extra_provenance.values()
        for source in sources
        if source.get("variant_source")
    }
    if source_kinds and source_kinds <= {"alternative"}:
        return "alternative_variant_forms_not_in_saldo"
    if "merged" in source_kinds or len(source_kinds) > 1:
        return "mixed_variant_form_difference"
    if source_kinds == {"primary"}:
        return "primary_variant_form_difference"
    if missing_forms and not extra_provenance:
        return "saldo_has_additional_forms"
    return "other_variant_paradigm_difference"


def _group_net_details(details: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        if row.get("stage") != "net":
            continue
        groups[(str(row.get("record_id") or ""), str(row.get("lemma") or ""))].append(row)
    return groups


def build_residuals(
    delta_summary: dict[str, Any],
    delta_details: list[dict[str, Any]],
    noun_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    artifacts = _artifact_index(noun_rows)
    groups = _group_net_details(delta_details)
    residuals: list[dict[str, Any]] = []
    resolved_rows = 0
    new_rows = 0

    for (record_id, lemma), rows in sorted(groups.items(), key=lambda item: (item[0][1].casefold(), item[0][0])):
        newly_bad = [
            row for row in rows
            if row.get("after_status") == "form_set_mismatch"
            and row.get("before_status") != "form_set_mismatch"
        ]
        resolved = [
            row for row in rows
            if row.get("before_status") == "form_set_mismatch"
            and row.get("after_status") != "form_set_mismatch"
        ]
        new_rows += len(newly_bad)
        resolved_rows += len(resolved)
        if not newly_bad:
            continue

        exemplar = newly_bad[0]
        generated = set(str(value) for value in exemplar.get("after_generated_forms", []))
        saldo = set(str(value) for value in exemplar.get("after_saldo_forms", []))
        extra = generated - saldo
        missing = saldo - generated
        candidates = artifacts.get((record_id, lemma), [])
        artifact = candidates[0] if candidates else None
        provenance = _extra_form_provenance(artifact, extra)
        method = str(exemplar.get("after_match_method") or "")
        reason = _reason(
            match_method=method,
            extra_provenance=provenance,
            missing_forms=missing,
        )
        residuals.append(
            {
                "record_id": record_id,
                "article_id": str((artifact or {}).get("article_id") or record_id),
                "lemma": lemma,
                "homonym_numbers": sorted({str(row.get("homonym_number") or "") for row in newly_bad}),
                "validation_rows": len(newly_bad),
                "legacy_statuses": sorted({str(row.get("before_status") or "") for row in newly_bad}),
                "current_status": "form_set_mismatch",
                "match_method": method,
                "variant_mode": str((artifact or {}).get("variant_mode") or "single"),
                "headings": list((artifact or {}).get("variant_lemmas") or [lemma]),
                "generated_forms": sorted(generated, key=str.casefold),
                "saldo_forms": sorted(saldo, key=str.casefold),
                "extra_from_saol": sorted(extra, key=str.casefold),
                "missing_from_saol": sorted(missing, key=str.casefold),
                "extra_form_provenance": provenance,
                "reason": reason,
            }
        )

    reason_counts = Counter(row["reason"] for row in residuals)
    mode_counts = Counter(row["variant_mode"] for row in residuals)
    summary = {
        "legacy_form_set_mismatch": int(delta_summary.get("legacy_form_set_mismatch", 0)),
        "current_form_set_mismatch": int(delta_summary.get("current_form_set_mismatch", 0)),
        "net_delta": int(delta_summary.get("net_delta", 0)),
        "new_residual_validation_rows": new_rows,
        "resolved_legacy_mismatch_rows": resolved_rows,
        "new_residual_articles": len(residuals),
        "net_identity_holds": new_rows - resolved_rows == int(delta_summary.get("net_delta", 0)),
        "reason_counts": dict(sorted(reason_counts.items())),
        "variant_mode_counts": dict(sorted(mode_counts.items())),
    }
    return summary, residuals


def render(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "SAOL14 residualer efter artikelvariantgenerering och variantmatchning",
        "",
        f"Legacy form_set_mismatch: {summary['legacy_form_set_mismatch']}",
        f"Current form_set_mismatch: {summary['current_form_set_mismatch']}",
        f"Nya residualrader: {summary['new_residual_validation_rows']}",
        f"Lösta gamla mismatchrader: {summary['resolved_legacy_mismatch_rows']}",
        f"Netto: {summary['net_delta']:+d}",
        f"Nettoidentitet  nya-lösta=netto: {'JA' if summary['net_identity_holds'] else 'NEJ'}",
        f"Nya residualartiklar efter sammanslagning av duplicerade rå-rader: {summary['new_residual_articles']}",
        "",
        "Orsaksgrupper:",
    ]
    lines.extend(f"  {count:5d}  {reason}" for reason, count in summary["reason_counts"].items())
    lines.extend(["", "Variantlägen:"])
    lines.extend(f"  {count:5d}  {mode}" for mode, count in summary["variant_mode_counts"].items())

    for row in rows:
        lines.extend(
            [
                "",
                "=" * 72,
                f"{row['lemma']}  article_id={row['article_id']} record_id={row['record_id']}",
                f"homonr: {', '.join(row['homonym_numbers']) or '–'}  rå-valideringsrader: {row['validation_rows']}",
                f"variant_mode: {row['variant_mode']}",
                f"rubriker: {', '.join(row['headings'])}",
                f"legacy: {', '.join(row['legacy_statuses'])}  current: {row['current_status']}",
                f"matchning: {row['match_method']}",
                f"orsak: {row['reason']}",
                "SAOL-former: " + (", ".join(row["generated_forms"]) or "–"),
                "SALDO-former: " + (", ".join(row["saldo_forms"]) or "–"),
                "Finns bara i SAOL: " + (", ".join(row["extra_from_saol"]) or "–"),
                "Finns bara i SALDO: " + (", ".join(row["missing_from_saol"]) or "–"),
                "Proveniens för SAOL-extra:",
            ]
        )
        if not row["extra_form_provenance"]:
            lines.append("  –")
        for form, sources in row["extra_form_provenance"].items():
            if not sources:
                lines.append(f"  {form}: okänd")
                continue
            rendered_sources = ", ".join(
                f"{source['heading']} [{source['variant_source']}]"
                for source in sources
            )
            lines.append(f"  {form}: {rendered_sources}")
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def analyze(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO_FORMS,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    delta_summary, delta_details = analyze_delta(
        saol_path,
        saldo_path,
        noun_forms_path,
        adjective_forms_path,
    )
    noun_rows = list(read_jsonl(noun_forms_path))
    return build_residuals(delta_summary, delta_details, noun_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze newly introduced residual SAOL/SALDO noun mismatches with form provenance"
    )
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    summary, rows = analyze(args.saol, args.saldo, args.noun_forms, args.adjective_forms)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary, rows), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_jsonl(args.jsonl, rows)

    print(f"Nya residualrader: {summary['new_residual_validation_rows']}")
    print(f"Lösta gamla mismatchrader: {summary['resolved_legacy_mismatch_rows']}")
    print(f"Netto: {summary['net_delta']:+d}")
    print(f"Nya residualartiklar: {summary['new_residual_articles']}")
    print(f"Nettoidentitet: {'JA' if summary['net_identity_holds'] else 'NEJ'}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
