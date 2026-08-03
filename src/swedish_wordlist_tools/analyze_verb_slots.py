from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .inflect import normalise_pattern
from .jsonl import read_jsonl
from .verb_slots import diagnose_verb_record, interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-slots.txt")
DEFAULT_JSON = Path("reports/saol14-verb-slots.json")
TEXT_HARD_CAP = 50


def _has_source_ellipsis(record: dict[str, Any]) -> bool:
    """Return whether the human-readable ``ordkl`` display contains ellipsis.

    Ellipsis is presentation metadata. It is deliberately not used as proof
    that the machine-readable ``text`` value is truncated.
    """
    ordkl = str(record.get("ordkl") or "")
    return "..." in ordkl or "…" in ordkl


def _external_lookup_candidate(record: dict[str, Any]) -> bool:
    """Return true for rows that hit the observed 50-character text cap."""
    return len(str(record.get("text") or "")) == TEXT_HARD_CAP


def _truncation_kind(record: dict[str, Any]) -> str | None:
    if _external_lookup_candidate(record):
        return "text_at_hard_cap"
    if _has_source_ellipsis(record):
        return "ordkl_ellipsis_but_text_below_cap"
    return None


def _length_summary(counter: Counter[int]) -> dict[str, Any]:
    if not counter:
        return {
            "records": 0,
            "minimum": 0,
            "maximum": 0,
            "most_common_lengths": {},
        }
    return {
        "records": sum(counter.values()),
        "minimum": min(counter),
        "maximum": max(counter),
        "most_common_lengths": dict(counter.most_common(20)),
    }


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    total = 0
    interpreted = 0
    unsupported: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    truncation_counts: Counter[str] = Counter()
    slot_counts: Counter[str] = Counter()
    all_text_lengths: Counter[int] = Counter()
    capped_text_lengths: Counter[int] = Counter()
    ordkl_ellipsis_lengths: Counter[int] = Counter()
    examples: dict[str, list[dict[str, str]]] = {}
    reason_examples: dict[str, list[dict[str, str]]] = {}
    truncation_examples: dict[str, list[dict[str, str]]] = {}

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        total += 1
        raw_text = str(record.get("text") or "")
        text_length = len(raw_text)
        all_text_lengths[text_length] += 1
        if text_length == TEXT_HARD_CAP:
            capped_text_lengths[text_length] += 1
        if _has_source_ellipsis(record):
            ordkl_ellipsis_lengths[text_length] += 1

        truncation_kind = _truncation_kind(record)
        if truncation_kind is not None:
            truncation_counts[truncation_kind] += 1
            truncation_examples.setdefault(truncation_kind, [])
            if len(truncation_examples[truncation_kind]) < 30:
                truncation_examples[truncation_kind].append({
                    "lemma": str(record.get("normaliserat_ord", "")),
                    "notation": raw_text,
                    "text_length": str(text_length),
                    "ordkl": str(record.get("ordkl", "")),
                    "source": str(record.get("source", "")),
                })

        slots = interpret_verb_slots(record)
        if slots is not None:
            interpreted += 1
            slot_counts.update(slots.slots())
            continue

        reason = diagnose_verb_record(record)
        reason_counts[reason] += 1
        pattern = normalise_pattern(record.get("text")) or "(none)"
        unsupported[pattern] += 1
        example = {
            "lemma": str(record.get("normaliserat_ord", "")),
            "notation": raw_text,
            "normalised": pattern,
            "stycke": str(record.get("stycke", "")),
            "ordkl": str(record.get("ordkl", "")),
        }
        examples.setdefault(pattern, [])
        if len(examples[pattern]) < 5:
            examples[pattern].append(example)
        reason_examples.setdefault(reason, [])
        if len(reason_examples[reason]) < 20:
            reason_examples[reason].append(example)

    return {
        "verb_records": total,
        "interpreted": interpreted,
        "coverage_percent": round(100 * interpreted / total, 2) if total else 0.0,
        "slot_counts": dict(slot_counts.most_common()),
        "text_hard_cap": TEXT_HARD_CAP,
        "text_length_distribution": {
            "all_verbs": _length_summary(all_text_lengths),
            "at_hard_cap": _length_summary(capped_text_lengths),
            "ordkl_ellipsis": _length_summary(ordkl_ellipsis_lengths),
        },
        "source_truncation_counts": dict(truncation_counts.most_common()),
        "source_truncation_examples": truncation_examples,
        "failure_reason_counts": dict(reason_counts.most_common()),
        "failure_reason_examples": reason_examples,
        "largest_unsupported_patterns": dict(unsupported.most_common(50)),
        "examples": {
            pattern: examples[pattern]
            for pattern, _count in unsupported.most_common(30)
        },
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Tolkade: {report['interpreted']}",
        f"Täckning: {report['coverage_percent']:.2f} %",
        f"Observerad hård maxlängd för text: {report['text_hard_cap']}",
        "",
        "Slots:",
    ]
    for slot, count in report["slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")

    lines.extend(["", "Längd på text-fältet:"])
    labels = {
        "all_verbs": "alla verb",
        "at_hard_cap": "exakt vid 50-teckensgränsen",
        "ordkl_ellipsis": "ordkl innehåller ellips",
    }
    for key, summary in report["text_length_distribution"].items():
        lines.append(
            f"  {labels[key]}: poster={summary['records']}, "
            f"min={summary['minimum']}, max={summary['maximum']}"
        )
        common = ", ".join(
            f"{length}:{count}"
            for length, count in summary["most_common_lengths"].items()
        )
        lines.append(f"    vanligaste längder: {common or '–'}")

    lines.extend(["", "Källfält:"])
    kind_labels = {
        "text_at_hard_cap": "text är exakt 50 tecken; kontrollkandidat",
        "ordkl_ellipsis_but_text_below_cap": (
            "ordkl har ellips men text är kortare än 50"
        ),
    }
    for kind, count in report["source_truncation_counts"].items():
        lines.append(f"  {count:6d}  {kind_labels.get(kind, kind)}")
    for kind, rows in report["source_truncation_examples"].items():
        lines.extend(["", f"Exempel: {kind_labels.get(kind, kind)}"])
        for row in rows[:15]:
            lines.append(
                f"  {row['lemma']} | len={row['text_length']} | "
                f"text={row['notation']!r} | ordkl={row['ordkl']!r}"
            )

    lines.extend(["", "Orsaker till otolkade verb:"])
    for reason, count in report["failure_reason_counts"].items():
        lines.append(f"  {count:6d}  {reason}")
    for reason, rows in report["failure_reason_examples"].items():
        lines.extend(["", f"Exempel: {reason}"])
        for row in rows[:10]:
            lines.append(
                f"  {row['lemma']} | stycke={row['stycke']!r} | "
                f"{row['normalised']}"
            )

    lines.extend(["", "Största ännu otolkade verbmönster:"])
    for pattern, count in report["largest_unsupported_patterns"].items():
        lines.append(f"  {count:6d}  {pattern}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure generic SAOL verb slot coverage")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verbposter: {report['verb_records']}")
    print(f"Tolkade: {report['interpreted']}")
    print(f"Täckning: {report['coverage_percent']:.2f} %")
    print(f"Text exakt 50 tecken: {report['source_truncation_counts'].get('text_at_hard_cap', 0)}")
    print(
        "Ordkl-ellips men text under 50: "
        f"{report['source_truncation_counts'].get('ordkl_ellipsis_but_text_below_cap', 0)}"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
