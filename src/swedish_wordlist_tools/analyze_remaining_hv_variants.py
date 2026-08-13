from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_current_hv_only import analyze as analyze_current_hv_only
from .analyze_x_routing import _is_hv
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-hv-variants.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-hv-variants.json")


def _key(value: Any) -> str:
    return clean_saol_word(value).casefold().strip()


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    current = analyze_current_hv_only(materialized)
    remaining = [
        row for row in current["remaining"]
        if row.get("classification") == "UNKNOWN_WORD"
    ]

    printed_non_hv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_non_hv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_normalized: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in materialized:
        if _is_hv(record):
            continue
        printed = _key(record.get("ord") or record.get("stycke"))
        normalized = _key(record.get("normaliserat_ord"))
        if printed:
            printed_non_hv[printed].append(record)
        if normalized:
            normalized_non_hv[normalized].append(record)
            by_normalized[normalized].append(record)

    rows: list[dict[str, Any]] = []
    evidence_counts: Counter[str] = Counter()

    for row in remaining:
        form = str(row.get("form") or "")
        form_key = _key(form)
        lemma = str(row.get("hv_lemma") or "")
        lemma_key = _key(lemma)
        evidence: list[str] = []

        exact_printed = printed_non_hv.get(form_key, [])
        exact_normalized = normalized_non_hv.get(form_key, [])
        sibling_variants = [
            record for record in by_normalized.get(lemma_key, [])
            if _key(record.get("ord") or record.get("stycke")) != lemma_key
        ]
        homonr0_variants = [
            record for record in sibling_variants
            if str(record.get("homonr") or "").strip() == "0"
        ]

        if exact_printed:
            evidence.append("EXACT_NON_HV_PRINTED_FORM")
        if exact_normalized:
            evidence.append("EXACT_NON_HV_NORMALIZED_FORM")
        if homonr0_variants:
            evidence.append("PARALLEL_HOMONR0_VARIANT_IN_TARGET_ARTICLE")
        elif sibling_variants:
            evidence.append("PARALLEL_PRINTED_VARIANT_IN_TARGET_ARTICLE")
        if not evidence:
            evidence.append("NO_STRUCTURAL_VARIANT_EVIDENCE")

        for item in evidence:
            evidence_counts[item] += 1

        def compact(record: dict[str, Any]) -> dict[str, Any]:
            return {
                "record_id": _record_id(record),
                "normaliserat_ord": clean_saol_word(record.get("normaliserat_ord")),
                "ord": clean_saol_word(record.get("ord") or record.get("stycke")),
                "homonr": str(record.get("homonr") or ""),
                "ordkl": str(record.get("ordkl") or ""),
                "text": str(record.get("text") or ""),
            }

        rows.append({
            "form": form,
            "hv_lemma": lemma,
            "gap_hypothesis": row.get("gap_hypothesis"),
            "evidence": evidence,
            "exact_printed_rows": [compact(r) for r in exact_printed],
            "exact_normalized_rows": [compact(r) for r in exact_normalized],
            "parallel_variant_rows": [compact(r) for r in sibling_variants],
        })

    rows.sort(key=lambda row: str(row["form"]).casefold())
    actionable = [
        row for row in rows
        if any(item.startswith("EXACT_NON_HV_") for item in row["evidence"])
    ]
    parallel_only = [
        row for row in rows
        if not any(item.startswith("EXACT_NON_HV_") for item in row["evidence"])
        and any("VARIANT_IN_TARGET_ARTICLE" in item for item in row["evidence"])
    ]

    return {
        "remaining_unknown": len(rows),
        "exact_structural_recoveries": len(actionable),
        "parallel_variant_context": len(parallel_only),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: strukturell variantaudit av kvarvarande hv-UNKNOWN",
        "",
        "EXACT_NON_HV_* betyder att samma skrivna form redan finns explicit på en",
        "icke-hv-rad och därför kan vara en integrationslucka. PARALLEL_* betyder",
        "bara att målartikeln också har en tryckt variant; det är diagnostik och",
        "räcker inte ensamt för att koppla hv-formen till den varianten.",
        "",
        f"Kvarvarande UNKNOWN: {report['remaining_unknown']}",
        f"Exakt strukturellt återvinningsbara: {report['exact_structural_recoveries']}",
        f"Endast parallell variantkontext: {report['parallel_variant_context']}",
        "Bevis:",
    ]
    for key, count in report["evidence_counts"].items():
        lines.append(f"  {count:4d}  {key}")

    for row in report["rows"]:
        if row["evidence"] == ["NO_STRUCTURAL_VARIANT_EVIDENCE"]:
            continue
        lines.append("")
        lines.append(
            f"{row['form']!r} <- {row['hv_lemma']} | {row['gap_hypothesis']} | "
            + ",".join(row["evidence"])
        )
        for item in row["exact_printed_rows"]:
            lines.append(f"  exact printed: {item['ord']} norm={item['normaliserat_ord']} hom={item['homonr']} ordkl={item['ordkl']!r}")
        for item in row["exact_normalized_rows"]:
            lines.append(f"  exact normalized: {item['ord']} norm={item['normaliserat_ord']} hom={item['homonr']} ordkl={item['ordkl']!r}")
        for item in row["parallel_variant_rows"][:4]:
            lines.append(f"  parallel variant: {item['ord']} norm={item['normaliserat_ord']} hom={item['homonr']} ordkl={item['ordkl']!r}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit structural variant evidence for remaining SAOL hv unknown forms")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Kvarvarande UNKNOWN: {report['remaining_unknown']}")
    print(f"Exakt strukturellt återvinningsbara: {report['exact_structural_recoveries']}")
    print(f"Endast parallell variantkontext: {report['parallel_variant_context']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
