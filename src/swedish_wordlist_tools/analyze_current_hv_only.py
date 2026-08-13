from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .build_shared_wordlist import build_rows
from .classify_hv_only import analyze as classify_hv_only
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-current-hv-only.txt")
DEFAULT_JSON = Path("reports/saol14-current-hv-only.json")


def _key(value: Any) -> str:
    return clean_saol_word(value).casefold().strip()


def _current_shared_forms(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """Return every form classified by the production shared-wordlist builder."""

    forms: dict[str, set[str]] = defaultdict(set)
    rows, _summary = build_rows(records)
    for row in rows:
        if row.get("classification") != "CLASSIFIED":
            continue
        written = clean_saol_word(row.get("form"))
        if written:
            forms[_key(written)].update(str(upos) for upos in row.get("upos", []))
    return forms


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    historical = classify_hv_only(materialized)
    current_forms = _current_shared_forms(materialized)

    recovered: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()

    for row in historical["rows"]:
        key = _key(row.get("form"))
        recovered_by = current_forms.get(key, set())
        if recovered_by:
            recovered.append({
                "form": row.get("form"),
                "hv_lemma": row.get("hv_lemma"),
                "old_classification": row.get("classification"),
                "recovered_by": sorted(recovered_by),
            })
            for upos in recovered_by:
                class_counts[upos] += 1
            continue
        remaining.append(row)
        gap_counts[str(row.get("gap_hypothesis") or "UNKNOWN")] += 1

    recovered.sort(key=lambda row: str(row["form"]).casefold())
    remaining.sort(key=lambda row: (str(row.get("classification")), str(row.get("form")).casefold()))
    return {
        "historical_hv_only": len(historical["rows"]),
        "recovered_by_current_shared": len(recovered),
        # Compatibility for callers of the earlier PRON/NUM/ADV-only audit.
        "recovered_by_current_extra_shared": len(recovered),
        "recovered_by_class": dict(sorted(class_counts.items())),
        "current_hv_only": len(remaining),
        "remaining_gap_hypotheses": dict(sorted(gap_counts.items())),
        "recovered": recovered,
        "remaining": remaining,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: hv-only jämfört med nuvarande shared-generatorer",
        "",
        "Den äldre hv-auditens restmängd jämförs här direkt mot de former som",
        "dagens produktionsbuilder klassificerar. Formen är verkligt hv-only först",
        "om den inte återfinns som CLASSIFIED i den färdiga ordlistan.",
        "",
        f"Historiskt hv-only: {report['historical_hv_only']}",
        f"Återfunna av nuvarande shared-builder: {report['recovered_by_current_shared']}",
        f"Verkligt hv-only nu: {report['current_hv_only']}",
        "Återfunna per klass:",
    ]
    for upos, count in report["recovered_by_class"].items():
        lines.append(f"  {count:4d}  {upos}")
    lines.append("Gap-hypotes för kvarvarande:")
    for gap, count in report["remaining_gap_hypotheses"].items():
        lines.append(f"  {count:4d}  {gap}")

    lines.extend(["", "=" * 78, "ÅTERFUNNA AV NUVARANDE SHARED-BUILDER"])
    for row in report["recovered"]:
        lines.append(
            f"  {row['form']!r} <- hv {row['hv_lemma']} | {','.join(row['recovered_by'])}"
        )

    lines.extend(["", "=" * 78, "VERKLIGT HV-ONLY"])
    for row in report["remaining"]:
        lines.append(
            f"  {row.get('form')!r} <- hv {row.get('hv_lemma')} | "
            f"{row.get('classification')} | {row.get('gap_hypothesis')}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit historical hv-only forms against current PRON/NUM/ADV")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Historiskt hv-only: {report['historical_hv_only']}")
    print(f"Återfunna av nuvarande shared-builder: {report['recovered_by_current_shared']}")
    print(f"Verkligt hv-only nu: {report['current_hv_only']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
