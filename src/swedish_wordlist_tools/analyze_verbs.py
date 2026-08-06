from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_slots import diagnose_verb_record, interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verbs.txt")
DEFAULT_JSON = Path("reports/saol14-verbs.json")


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _excluded_reason(lemma: str) -> str | None:
    if not lemma:
        return None
    if lemma.startswith("-") or lemma.endswith("-"):
        return "suffix_or_prefix_lemma"
    if " " in lemma:
        return "multiword_lemma"
    return None


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record
        for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "VERB"
    ]
    diagnosis_counts: Counter[str] = Counter()
    exclusion_counts: Counter[str] = Counter()
    diagnosis_samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    interpreted = 0
    excluded = 0

    for record in records:
        lemma = _value(record, "normaliserat_ord")
        exclusion = _excluded_reason(lemma)
        diagnosis = diagnose_verb_record(record)
        slots = interpret_verb_slots(record) if exclusion is None else None
        if exclusion is not None:
            excluded += 1
            exclusion_counts[exclusion] += 1
        elif slots is not None:
            interpreted += 1
        else:
            diagnosis_counts[diagnosis] += 1
            if len(diagnosis_samples[diagnosis]) < 30:
                diagnosis_samples[diagnosis].append(
                    {
                        "lemma": lemma,
                        "homonr": _value(record, "homonr"),
                        "text": _value(record, "text") or "(none)",
                        "stycke": _value(record, "stycke"),
                    }
                )
        rows.append(
            {
                "lemma": lemma,
                "homonym_number": _value(record, "homonr"),
                "text": _value(record, "text") or None,
                "stycke": _value(record, "stycke"),
                "diagnosis": diagnosis,
                "excluded_reason": exclusion,
                "interpreted": slots is not None,
                "forms": list(slots.written_forms()) if slots else [],
            }
        )

    remaining = len(records) - interpreted - excluded
    return {
        "verb_records": len(records),
        "interpreted_playable_records": interpreted,
        "intentionally_excluded_records": excluded,
        "genuinely_uninterpreted_records": remaining,
        "exclusion_counts": dict(exclusion_counts.most_common()),
        "diagnosis_counts": dict(diagnosis_counts.most_common()),
        "diagnosis_samples": dict(diagnosis_samples),
        "records": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Tolkade spelbara poster: {report['interpreted_playable_records']}",
        f"Avsiktligt exkluderade poster: {report['intentionally_excluded_records']}",
        f"Verkligt otolkade poster: {report['genuinely_uninterpreted_records']}",
        "",
        "Avsiktligt exkluderade:",
    ]
    if not report["exclusion_counts"]:
        lines.append("  (inga)")
    for reason, count in report["exclusion_counts"].items():
        lines.append(f"  {count:6d}  {reason}")
    lines.extend(["", "Verkligt otolkade diagnoser:"])
    if not report["diagnosis_counts"]:
        lines.append("  (inga)")
    for reason, count in report["diagnosis_counts"].items():
        lines.append(f"  {count:6d}  {reason}")
    lines.extend(["", "Exempel per återstående diagnos:"])
    if not report["diagnosis_samples"]:
        lines.append("  (inga)")
    for reason, samples in report["diagnosis_samples"].items():
        lines.append(f"  {reason}:")
        for row in samples:
            lines.append(
                f"    {row['lemma']} (homonr={row['homonr'] or '-'}) | "
                f"text={row['text']!r} | stycke={row['stycke']!r}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory SAOL14 verb interpretation")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verbposter: {report['verb_records']}")
    print(f"Tolkade spelbara poster: {report['interpreted_playable_records']}")
    print(f"Avsiktligt exkluderade poster: {report['intentionally_excluded_records']}")
    print(f"Verkligt otolkade poster: {report['genuinely_uninterpreted_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
