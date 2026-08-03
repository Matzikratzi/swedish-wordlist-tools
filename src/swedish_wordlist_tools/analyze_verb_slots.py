from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .inflect import normalise_pattern
from .jsonl import read_jsonl
from .verb_slots import diagnose_verb_record, interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-slots.txt")
DEFAULT_JSON = Path("reports/saol14-verb-slots.json")
_TRUNCATION_MARK_RE = re.compile(r"(?:\.\.\.|…)")
_SUSPICIOUS_END_RE = re.compile(
    r"(?:\bpre(?:s)?\.?|\bimper\.?|\bperf\.?|[-+][A-Za-zÅÄÖåäöÉéÜü]{0,2}|\b[A-Za-zÅÄÖåäöÉéÜü]{1,3})$",
    re.IGNORECASE,
)


def _truncation_kind(record: dict[str, Any]) -> str | None:
    """Classify source-field truncation without guessing grammatical forms.

    ``certain`` means that the source metadata itself contains an ellipsis.
    ``suspected`` is reserved for a text field ending in an incomplete label or
    very short fragment, and is reported separately because short verb forms
    such as ``går`` and ``ser`` can be legitimate.
    """
    ordkl = str(record.get("ordkl") or "")
    text = str(record.get("text") or "").strip()
    if _TRUNCATION_MARK_RE.search(ordkl) or _TRUNCATION_MARK_RE.search(text):
        return "certain"
    if text and _SUSPICIOUS_END_RE.search(text):
        return "suspected"
    return None


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    total = 0
    interpreted = 0
    unsupported = Counter()
    reason_counts = Counter()
    truncation_counts = Counter()
    slot_counts = Counter()
    examples: dict[str, list[dict[str, str]]] = {}
    reason_examples: dict[str, list[dict[str, str]]] = {}
    truncation_examples: dict[str, list[dict[str, str]]] = {}

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        total += 1

        truncation_kind = _truncation_kind(record)
        if truncation_kind is not None:
            truncation_counts[truncation_kind] += 1
            truncation_examples.setdefault(truncation_kind, [])
            if len(truncation_examples[truncation_kind]) < 30:
                truncation_examples[truncation_kind].append({
                    "lemma": str(record.get("normaliserat_ord", "")),
                    "notation": str(record.get("text", "")),
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
            "notation": str(record.get("text", "")),
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
        "",
        "Slots:",
    ]
    for slot, count in report["slot_counts"].items():
        lines.append(f"  {count:6d}  {slot}")

    lines.extend(["", "Avklippta källfält:"])
    for kind, count in report["source_truncation_counts"].items():
        label = "säkert avklippta" if kind == "certain" else "misstänkt avklippta"
        lines.append(f"  {count:6d}  {label}")
    for kind, examples in report["source_truncation_examples"].items():
        label = "säkert" if kind == "certain" else "misstänkt"
        lines.extend(["", f"Exempel: {label} avklippta"])
        for example in examples[:15]:
            lines.append(
                f"  {example['lemma']} | text={example['notation']!r} | ordkl={example['ordkl']!r}"
            )

    lines.extend(["", "Orsaker till otolkade verb:"])
    for reason, count in report["failure_reason_counts"].items():
        lines.append(f"  {count:6d}  {reason}")

    for reason, examples in report["failure_reason_examples"].items():
        lines.extend(["", f"Exempel: {reason}"])
        for example in examples[:10]:
            lines.append(
                f"  {example['lemma']} | stycke={example['stycke']!r} | {example['normalised']}"
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
    print(f"Säkert avklippta: {report['source_truncation_counts'].get('certain', 0)}")
    print(f"Misstänkt avklippta: {report['source_truncation_counts'].get('suspected', 0)}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
