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
_INCOMPLETE_LABEL_RE = re.compile(
    r"(?:\bpre(?:s)?\.?|\bpret\.?|\bimper\.?|\bperf\.?|\bsup\.?)$",
    re.IGNORECASE,
)
_UNSIGNED_SHORT_FRAGMENT_RE = re.compile(
    r"(?:^|[\s,;:])[A-Za-zÅÄÖåäöÉéÜü]{1,3}$"
)
_SIGNED_SHORT_FRAGMENT_RE = re.compile(
    r"(?:^|[\s,;:])[-+][A-Za-zÅÄÖåäöÉéÜü]{1,2}$"
)
_DANGLING_END_RE = re.compile(r"[-+,:;]$")


def _has_source_ellipsis(record: dict[str, Any]) -> bool:
    ordkl = str(record.get("ordkl") or "")
    text = str(record.get("text") or "")
    return bool(_TRUNCATION_MARK_RE.search(ordkl) or _TRUNCATION_MARK_RE.search(text))


def _external_lookup_candidate(record: dict[str, Any]) -> bool:
    """Return true only for source rows that plausibly need external repair.

    An ellipsis in ``ordkl`` proves that the displayed source field was cut,
    but that alone does not mean the machine-readable ``text`` is unusable.
    External lookup is proposed only when the text itself also ends like an
    incomplete grammatical label, a dangling notation character, or a very
    short fragment in a longer comma-separated paradigm. Signed forms of three
    letters such as ``-gör`` and ``-för`` are treated as complete; signed
    fragments must be at most two letters, while unsigned fragments may be at
    most three letters (for example ``sju`` in a truncated ``sjunger``).
    """
    if not _has_source_ellipsis(record):
        return False
    text = str(record.get("text") or "").strip()
    if not text:
        return True
    if _INCOMPLETE_LABEL_RE.search(text) or _DANGLING_END_RE.search(text):
        return True
    if "," not in text:
        return False
    return bool(
        _SIGNED_SHORT_FRAGMENT_RE.search(text)
        or _UNSIGNED_SHORT_FRAGMENT_RE.search(text)
    )


def _truncation_kind(record: dict[str, Any]) -> str | None:
    if _external_lookup_candidate(record):
        return "external_lookup_candidate"
    if _has_source_ellipsis(record):
        return "ellipsis_but_text_usable"
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
    labels = {
        "external_lookup_candidate": "kandidater för komplettering från svenska.se",
        "ellipsis_but_text_usable": "ellips i källfältet men användbar text",
    }
    for kind, count in report["source_truncation_counts"].items():
        lines.append(f"  {count:6d}  {labels.get(kind, kind)}")
    for kind, examples in report["source_truncation_examples"].items():
        lines.extend(["", f"Exempel: {labels.get(kind, kind)}"])
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
    print(
        "Kandidater för svenska.se: "
        f"{report['source_truncation_counts'].get('external_lookup_candidate', 0)}"
    )
    print(
        "Ellips men användbar text: "
        f"{report['source_truncation_counts'].get('ellipsis_but_text_usable', 0)}"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
