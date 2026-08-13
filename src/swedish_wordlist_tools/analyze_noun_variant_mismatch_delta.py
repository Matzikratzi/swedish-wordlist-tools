from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .canonical_form_artifacts import DEFAULT_ADJECTIVE_FORMS, DEFAULT_NOUN_FORMS
from .generate_noun_forms import generate_noun_artifact
from .jsonl import read_jsonl
from .revalidate_direct_forms_core import revalidate_direct_forms
from .saldo_form_artifact import DEFAULT_SALDO_FORMS
from .validate_direct_forms import DEFAULT_SAOL

DEFAULT_TEXT = Path("reports/saol14-noun-variant-mismatch-delta.txt")
DEFAULT_SUMMARY = Path("reports/saol14-noun-variant-mismatch-delta-summary.json")
DEFAULT_JSONL = Path("reports/saol14-noun-variant-mismatch-delta.jsonl")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _strip_variant_metadata(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep grouped form unions but disable article-variant SALDO matching."""

    result: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy.pop("variant_paradigms", None)
        copy.pop("variant_lemmas", None)
        result.append(copy)
    return result


def _row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("record_id") or ""),
        str(row.get("homonym_number") or ""),
        str(row.get("lemma") or ""),
        str(row.get("upos") or ""),
        str(row.get("notation") or ""),
    )


def _index(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[_row_key(row)].append(row)
    for values in result.values():
        values.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
    return result


def _scenario(
    *,
    saol: Path,
    saldo: Path,
    noun_forms: Path,
    adjective_forms: Path,
    directory: Path,
    name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    jsonl = directory / f"{name}.jsonl"
    summary = directory / f"{name}-summary.json"
    result = revalidate_direct_forms(
        saol,
        saldo,
        jsonl,
        summary,
        noun_forms_path=noun_forms,
        adjective_forms_path=adjective_forms,
    )
    return result, list(read_jsonl(jsonl))


def _compare_rows(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
    *,
    stage: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    before = _index(before_rows)
    after = _index(after_rows)
    details: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()

    for key in sorted(set(before) | set(after), key=lambda item: (item[2].casefold(), item[0], item[1])):
        left = before.get(key, [])
        right = after.get(key, [])
        for i in range(max(len(left), len(right))):
            a = left[i] if i < len(left) else None
            b = right[i] if i < len(right) else None
            old_status = str(a.get("status")) if a else "no_match"
            new_status = str(b.get("status")) if b else "no_match"
            transitions[f"{old_status}->{new_status}"] += 1
            if old_status == new_status and (
                (a or {}).get("generated_forms") == (b or {}).get("generated_forms")
                and (a or {}).get("saldo_forms") == (b or {}).get("saldo_forms")
            ):
                continue
            details.append({
                "stage": stage,
                "record_id": key[0],
                "homonym_number": key[1],
                "lemma": key[2],
                "upos": key[3],
                "notation": key[4],
                "before_status": old_status,
                "after_status": new_status,
                "before_generated_forms": (a or {}).get("generated_forms", []),
                "after_generated_forms": (b or {}).get("generated_forms", []),
                "before_saldo_forms": (a or {}).get("saldo_forms", []),
                "after_saldo_forms": (b or {}).get("saldo_forms", []),
                "before_match_method": (a or {}).get("match_method", "no_match"),
                "after_match_method": (b or {}).get("match_method", "no_match"),
            })
    return details, transitions


def _mismatch(summary: dict[str, Any]) -> int:
    return int(summary.get("status_counts", {}).get("form_set_mismatch", 0))


def analyze(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO_FORMS,
    noun_forms_path: Path = DEFAULT_NOUN_FORMS,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_rows = list(read_jsonl(saol_path))
    legacy_noun_rows, _comparisons, legacy_noun_summary = generate_noun_artifact(raw_rows)
    grouped_rows = list(read_jsonl(noun_forms_path))
    grouped_direct_rows = _strip_variant_metadata(grouped_rows)

    with tempfile.TemporaryDirectory(prefix="saol-mismatch-delta-") as tmp:
        directory = Path(tmp)
        legacy_path = directory / "legacy-noun.jsonl"
        grouped_direct_path = directory / "grouped-direct-noun.jsonl"
        _write_jsonl(legacy_path, legacy_noun_rows)
        _write_jsonl(grouped_direct_path, grouped_direct_rows)

        legacy_summary, legacy_validation = _scenario(
            saol=saol_path,
            saldo=saldo_path,
            noun_forms=legacy_path,
            adjective_forms=adjective_forms_path,
            directory=directory,
            name="legacy",
        )
        grouped_direct_summary, grouped_direct_validation = _scenario(
            saol=saol_path,
            saldo=saldo_path,
            noun_forms=grouped_direct_path,
            adjective_forms=adjective_forms_path,
            directory=directory,
            name="grouped-direct",
        )
        current_summary, current_validation = _scenario(
            saol=saol_path,
            saldo=saldo_path,
            noun_forms=noun_forms_path,
            adjective_forms=adjective_forms_path,
            directory=directory,
            name="current",
        )

    generator_details, generator_transitions = _compare_rows(
        legacy_validation, grouped_direct_validation, stage="variant_form_generation"
    )
    matching_details, matching_transitions = _compare_rows(
        grouped_direct_validation, current_validation, stage="article_variant_matching"
    )
    total_details, total_transitions = _compare_rows(
        legacy_validation, current_validation, stage="net"
    )

    legacy_mismatch = _mismatch(legacy_summary)
    grouped_direct_mismatch = _mismatch(grouped_direct_summary)
    current_mismatch = _mismatch(current_summary)
    summary = {
        "legacy_noun_generated_rows": legacy_noun_summary["generated_noun_records"],
        "grouped_noun_rows": len(grouped_rows),
        "legacy_matched_records": legacy_summary["matched_records"],
        "grouped_direct_matched_records": grouped_direct_summary["matched_records"],
        "current_matched_records": current_summary["matched_records"],
        "legacy_form_set_mismatch": legacy_mismatch,
        "grouped_direct_form_set_mismatch": grouped_direct_mismatch,
        "current_form_set_mismatch": current_mismatch,
        "variant_form_generation_delta": grouped_direct_mismatch - legacy_mismatch,
        "article_variant_matching_delta": current_mismatch - grouped_direct_mismatch,
        "net_delta": current_mismatch - legacy_mismatch,
        "reproduces_historical_3098": legacy_mismatch == 3098,
        "generator_status_transitions": dict(sorted(generator_transitions.items())),
        "matching_status_transitions": dict(sorted(matching_transitions.items())),
        "net_status_transitions": dict(sorted(total_transitions.items())),
        "generator_changed_rows": len(generator_details),
        "matching_changed_rows": len(matching_details),
        "net_changed_rows": len(total_details),
    }
    details = [*generator_details, *matching_details, *total_details]
    return summary, details


def render(summary: dict[str, Any], details: list[dict[str, Any]]) -> str:
    lines = [
        "SAOL14 noun variant mismatch delta",
        "",
        f"Legacy radlokal noun-generator: {summary['legacy_form_set_mismatch']} form_set_mismatch",
        f"Grouped variantformer + direkt match: {summary['grouped_direct_form_set_mismatch']} form_set_mismatch",
        f"Grouped variantformer + variantmatchning: {summary['current_form_set_mismatch']} form_set_mismatch",
        "",
        f"Variantformgeneratorns effekt: {summary['variant_form_generation_delta']:+d}",
        f"Variantmatchningens effekt: {summary['article_variant_matching_delta']:+d}",
        f"Netto: {summary['net_delta']:+d}",
        f"Reproducerar historiska 3098: {'JA' if summary['reproduces_historical_3098'] else 'NEJ'}",
        "",
        f"Matchade poster legacy/grouped-direct/current: {summary['legacy_matched_records']} / {summary['grouped_direct_matched_records']} / {summary['current_matched_records']}",
        "",
        "Statusövergångar när variantformer införs:",
    ]
    lines.extend(f"  {count:5d}  {transition}" for transition, count in summary["generator_status_transitions"].items())
    lines.extend(["", "Statusövergångar när variantmatchning införs:"])
    lines.extend(f"  {count:5d}  {transition}" for transition, count in summary["matching_status_transitions"].items())
    lines.extend(["", "Nettoövergångar legacy -> current:"])
    lines.extend(f"  {count:5d}  {transition}" for transition, count in summary["net_status_transitions"].items())

    for stage, heading in (
        ("variant_form_generation", "Exempel: variantformgeneratorn"),
        ("article_variant_matching", "Exempel: variantmatchningen"),
        ("net", "Exempel: netto legacy -> current"),
    ):
        selected = [row for row in details if row["stage"] == stage]
        if not selected:
            continue
        lines.extend(["", f"{heading} ({len(selected)} ändrade rader):"])
        for row in selected[:80]:
            lines.append(
                f"  {row['lemma']} ({row['homonym_number']}) id={row['record_id']} | "
                f"{row['before_status']} -> {row['after_status']} | "
                f"{row['before_match_method']} -> {row['after_match_method']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain the 3098 -> current SAOL/SALDO noun mismatch delta")
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    summary, details = analyze(args.saol, args.saldo, args.noun_forms, args.adjective_forms)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary, details), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_jsonl(args.jsonl, details)

    print(f"Legacy mismatch: {summary['legacy_form_set_mismatch']}")
    print(f"Grouped + direkt match: {summary['grouped_direct_form_set_mismatch']}")
    print(f"Current mismatch: {summary['current_form_set_mismatch']}")
    print(f"Variantformgenerator: {summary['variant_form_generation_delta']:+d}")
    print(f"Variantmatchning: {summary['article_variant_matching_delta']:+d}")
    print(f"Netto: {summary['net_delta']:+d}")
    print(f"Reproducerar 3098: {'JA' if summary['reproduces_historical_3098'] else 'NEJ'}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
