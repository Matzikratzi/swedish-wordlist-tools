from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _is_hv
from .classify_hv_only import analyze as classify_hv_only
from .generate_adverb_forms import generated_row as generated_adverb_row
from .generate_numeral_forms import generated_row as generated_numeral_row
from .generate_pronoun_forms import generated_row as generated_pronoun_row
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word
from .saol_wordclasses import classes_from_record, record_for_class

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-current-hv-only.txt")
DEFAULT_JSON = Path("reports/saol14-current-hv-only.json")
_EXTRA_CLASSES = frozenset({"PRON", "NUM", "ADV"})


def _key(value: Any) -> str:
    return clean_saol_word(value).casefold().strip()


def _extra_shared_forms(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    forms: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if _is_hv(record):
            continue
        for upos in classes_from_record(record):
            if upos not in _EXTRA_CLASSES:
                continue
            class_record = record_for_class(record, upos)
            if upos == "PRON":
                row = generated_pronoun_row(class_record)
            elif upos == "NUM":
                row = generated_numeral_row(class_record)
            else:
                row = generated_adverb_row(class_record)
            if row is None:
                continue
            for form in row.get("forms", []):
                written = clean_saol_word(form.get("written_form"))
                if written:
                    forms[_key(written)].add(upos)
    return forms


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    historical = classify_hv_only(materialized)
    extra_forms = _extra_shared_forms(materialized)

    recovered: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()

    for row in historical["rows"]:
        key = _key(row.get("form"))
        recovered_by = extra_forms.get(key, set())
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
        "Den äldre hv-auditen verifierar NOUN/ADJ/VERB. Här jämförs dess restmängd",
        "också mot dagens PRON/NUM/ADV-generatorer. Formen är verkligt hv-only först",
        "om ingen av dessa generatorer återfinner den.",
        "",
        f"Historiskt hv-only: {report['historical_hv_only']}",
        f"Återfunna av PRON/NUM/ADV: {report['recovered_by_current_extra_shared']}",
        f"Verkligt hv-only nu: {report['current_hv_only']}",
        "Återfunna per klass:",
    ]
    for upos, count in report["recovered_by_class"].items():
        lines.append(f"  {count:4d}  {upos}")
    lines.append("Gap-hypotes för kvarvarande:")
    for gap, count in report["remaining_gap_hypotheses"].items():
        lines.append(f"  {count:4d}  {gap}")

    lines.extend(["", "=" * 78, "ÅTERFUNNA AV NUVARANDE SHARED"])
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
    print(f"Återfunna av PRON/NUM/ADV: {report['recovered_by_current_extra_shared']}")
    print(f"Verkligt hv-only nu: {report['current_hv_only']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
