from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl


DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_OUTPUT = Path("data/processed/saol14-common-forms.txt")
DEFAULT_REPORT = Path("reports/saol14-common-forms.json")


# The first implementation is deliberately conservative: only exact, well
# understood SAOL14 patterns are expanded. The lemma itself is always included.
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


@dataclass(frozen=True)
class GeneratedEntry:
    lemma: str
    pattern: str
    forms: tuple[str, ...]


def normalise_pattern(value: Any) -> str | None:
    if value is None:
        return None
    pattern = str(value).strip()
    if not pattern or pattern == "(null)":
        return None
    return pattern


def generate_forms(lemma: str, pattern: str | None) -> tuple[str, ...] | None:
    """Generate forms for one exact supported SAOL14 pattern.

    Returns ``None`` for unsupported or missing patterns. The returned tuple
    starts with the lemma and contains no duplicates.
    """
    lemma = lemma.strip()
    if not lemma or pattern not in COMMON_PATTERNS:
        return None

    forms: list[str] = []
    seen: set[str] = set()
    for form in (lemma, *(lemma + suffix for suffix in COMMON_PATTERNS[pattern])):
        if form not in seen:
            seen.add(form)
            forms.append(form)
    return tuple(forms)


def generate_entry(record: dict[str, Any]) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    forms = generate_forms(lemma, pattern)
    if forms is None or pattern is None:
        return None
    return GeneratedEntry(lemma=lemma, pattern=pattern, forms=forms)


def iter_generated_entries(records: Iterable[dict[str, Any]]) -> Iterable[GeneratedEntry]:
    for record in records:
        entry = generate_entry(record)
        if entry is not None:
            yield entry


def build_wordlist(input_path: Path, output_path: Path) -> dict[str, Any]:
    source_records = 0
    supported_records = 0
    duplicate_forms = 0
    pattern_counts = {pattern: 0 for pattern in COMMON_PATTERNS}
    forms: list[str] = []
    seen: set[str] = set()

    for record in read_jsonl(input_path):
        source_records += 1
        entry = generate_entry(record)
        if entry is None:
            continue

        supported_records += 1
        pattern_counts[entry.pattern] += 1
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
        "coverage_percent": round(100 * supported_records / source_records, 2)
        if source_records
        else 0.0,
        "unique_forms": len(forms),
        "duplicate_forms": duplicate_forms,
        "pattern_counts": {
            pattern: count
            for pattern, count in sorted(
                pattern_counts.items(), key=lambda item: (-item[1], item[0])
            )
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate word forms for common SAOL14 inflection patterns"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_wordlist(args.input, args.output)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Poster i källfilen: {report['source_records']}")
    print(f"Poster med stödda mönster: {report['supported_records']}")
    print(f"Täckning: {report['coverage_percent']:.2f} %")
    print(f"Unika ordformer: {report['unique_forms']}")
    print(f"Ordlista: {args.output}")
    print(f"Rapport: {args.report}")


if __name__ == "__main__":
    main()
