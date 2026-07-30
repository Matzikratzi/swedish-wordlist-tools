from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_OUTPUT = Path("data/processed/saol14-common-forms.txt")
DEFAULT_REPORT = Path("reports/saol14-common-forms.json")
EXPLICIT_PATTERN_GROUP = "explicit böjningsform"

# Exact suffix-only patterns that have been manually reviewed.
COMMON_PATTERNS: dict[str, tuple[str, ...]] = {
    "+en +er": ("en", "er"),
    "+en +ar": ("en", "ar"),
    "+et; pl. +": ("et", ""),
    "+en": ("en",),
    "+t +a": ("t", "a"),
    "+de +t": ("de", "t"),
    "+t +n": ("t", "n"),
    "+n": ("n",),
    "+et": ("et",),
    "+n +r": ("n", "r"),
    "+n +er": ("n", "er"),
}

_LABELS = {"pl.", "best.", "pres.", "pret.", "sup.", "imper.", "komp.", "superl."}


@dataclass(frozen=True)
class GeneratedEntry:
    lemma: str
    pattern: str
    forms: tuple[str, ...]
    pattern_group: str = ""


def normalise_pattern(value: Any) -> str | None:
    if value is None:
        return None
    pattern = str(value).strip()
    if not pattern or pattern == "(null)":
        return None
    return pattern


def _attach_suffix(lemma: str, suffix: str) -> str:
    """Attach a suffix to the inflected word, not a following particle/pronoun."""
    head, separator, tail = lemma.partition(" ")
    inflected = head + suffix
    return inflected + (separator + tail if separator else "")


def _explicit_pattern_forms(lemma: str, pattern: str) -> tuple[str, ...] | None:
    """Read conservative patterns containing complete forms, e.g. '+n klockor'."""
    cleaned = pattern.replace(";", " ; ")
    tokens = cleaned.split()
    candidates: list[str] = []
    for token in tokens:
        stripped = token.strip(",;")
        if not stripped or stripped in _LABELS or stripped == ";":
            continue
        if stripped.startswith("+"):
            candidates.append(_attach_suffix(lemma, stripped[1:]))
        elif re.fullmatch(r"[A-Za-zÅÄÖåäöÉéÜü-]+", stripped):
            # An explicit SAOL form is already complete and must not be appended.
            candidates.append(stripped)
        else:
            return None

    # Only classify this as an explicit pattern when at least one complete form occurs.
    if not any(not token.strip(",;").startswith("+") and token.strip(",;") not in _LABELS
               for token in tokens if token.strip(",;") and token.strip(",;") != ";"):
        return None
    return _deduplicate((lemma, *candidates))


def _deduplicate(forms: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for form in forms:
        if form and form not in seen:
            seen.add(form)
            result.append(form)
    return tuple(result)


def generate_forms(lemma: str, pattern: str | None) -> tuple[str, ...] | None:
    lemma = lemma.strip()
    if not lemma or pattern is None:
        return None

    if pattern in COMMON_PATTERNS:
        return _deduplicate(
            (lemma, *(_attach_suffix(lemma, suffix) for suffix in COMMON_PATTERNS[pattern]))
        )
    return _explicit_pattern_forms(lemma, pattern)


def generate_entry(record: dict[str, Any]) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    forms = generate_forms(lemma, pattern)
    if forms is None or pattern is None:
        return None
    group = pattern if pattern in COMMON_PATTERNS else EXPLICIT_PATTERN_GROUP
    return GeneratedEntry(lemma=lemma, pattern=pattern, forms=forms, pattern_group=group)


def iter_generated_entries(records: Iterable[dict[str, Any]]) -> Iterable[GeneratedEntry]:
    for record in records:
        entry = generate_entry(record)
        if entry is not None:
            yield entry


def build_wordlist(input_path: Path, output_path: Path) -> dict[str, Any]:
    source_records = 0
    supported_records = 0
    duplicate_forms = 0
    pattern_counts: Counter[str] = Counter()
    forms: list[str] = []
    seen: set[str] = set()

    for record in read_jsonl(input_path):
        source_records += 1
        entry = generate_entry(record)
        if entry is None:
            continue
        supported_records += 1
        pattern_counts[entry.pattern_group] += 1
        for form in entry.forms:
            if form in seen:
                duplicate_forms += 1
                continue
            seen.add(form)
            forms.append(form)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(forms) + ("\n" if forms else ""), encoding="utf-8")
    return {
        "source": str(input_path),
        "output": str(output_path),
        "source_records": source_records,
        "supported_records": supported_records,
        "unsupported_records": source_records - supported_records,
        "coverage_percent": round(100 * supported_records / source_records, 2) if source_records else 0.0,
        "unique_forms": len(forms),
        "duplicate_forms": duplicate_forms,
        "pattern_counts": dict(pattern_counts.most_common()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate word forms from conservative SAOL14 patterns")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_wordlist(args.input, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster i källfilen: {report['source_records']}")
    print(f"Poster med stödda mönster: {report['supported_records']}")
    print(f"Täckning: {report['coverage_percent']:.2f} %")
    print(f"Unika ordformer: {report['unique_forms']}")
    print(f"Ordlista: {args.output}")
    print(f"Rapport: {args.report}")


if __name__ == "__main__":
    main()
