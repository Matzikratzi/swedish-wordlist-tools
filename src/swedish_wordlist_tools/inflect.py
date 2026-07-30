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

_LABELS = {
    "pl.", "best.", "pres.", "pret.", "sup.", "imper.", "komp.", "superl.",
    "pl", "best", "pres", "pret", "sup", "imper", "komp", "superl",
}
_ALTERNATIVE_MARKERS = {"el.", "el"}
_CONTROL_MARKERS = {"H"}
_TOKEN_RE = re.compile(
    r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+|pl\.|best\.|pres\.|pret\.|sup\.|imper\.|komp\.|superl\.|el\.|[;,]"
)


@dataclass(frozen=True)
class GeneratedEntry:
    lemma: str
    pattern: str
    forms: tuple[str, ...]
    pattern_group: str = ""
    form_kinds: tuple[str, ...] = ()


def normalise_pattern(value: Any) -> str | None:
    if value is None:
        return None
    pattern = str(value).strip()
    if not pattern or pattern == "(null)":
        return None
    return pattern


def _split_inflected_word(lemma: str) -> tuple[str, str]:
    head, separator, tail = lemma.partition(" ")
    return head, separator + tail if separator else ""


def _attach_suffix(lemma: str, suffix: str) -> str:
    head, tail = _split_inflected_word(lemma)
    return head + suffix + tail


def _replace_final_component(lemma: str, replacement: str) -> str | None:
    replacement = replacement.lstrip("-")
    if not replacement:
        return None
    head, tail = _split_inflected_word(lemma)
    anchor = replacement[0].casefold()
    positions = [index for index, char in enumerate(head) if char.casefold() == anchor]
    if not positions:
        return None
    return head[: positions[-1]] + replacement + tail


def _context_kind(context: str, explicit: bool) -> str:
    if context == "definite_plural":
        return "definite_plural"
    if context == "plural":
        return "plural"
    if context == "definite":
        return "definite_singular"
    return "explicit" if explicit else "derived"


def _deduplicate_tagged(forms: Iterable[tuple[str, str]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    result: list[str] = []
    kinds: list[str] = []
    seen: set[str] = set()
    for form, kind in forms:
        if form and form not in seen:
            seen.add(form)
            result.append(form)
            kinds.append(kind)
    return tuple(result), tuple(kinds)


def _explicit_pattern_forms(lemma: str, pattern: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    tokens = _TOKEN_RE.findall(pattern)
    tagged: list[tuple[str, str]] = [(lemma, "lemma")]
    context = "default"
    saw_explicit = False
    saw_alternative = False
    pending_best = False

    for raw in tokens:
        token = raw.strip()
        lower = token.casefold()

        if token in {";", ","}:
            continue
        if token in _CONTROL_MARKERS:
            continue
        if lower in _ALTERNATIVE_MARKERS:
            saw_alternative = True
            continue
        if lower in {label.casefold() for label in _LABELS}:
            if lower.startswith("best"):
                pending_best = True
                context = "definite"
            elif lower.startswith("pl"):
                context = "definite_plural" if pending_best else "plural"
                pending_best = False
            continue
        if token.startswith("+"):
            tagged.append((_attach_suffix(lemma, token[1:]), _context_kind(context, explicit=False)))
            continue
        if token.startswith("-"):
            form = _replace_final_component(lemma, token)
            if form is None:
                return None
            tagged.append((form, _context_kind(context, explicit=True)))
            saw_explicit = True
            continue
        if re.fullmatch(r"[A-Za-zÅÄÖåäöÉéÜü]+", token):
            tagged.append((token, _context_kind(context, explicit=True)))
            saw_explicit = True
            continue
        return None

    if not (saw_explicit or saw_alternative):
        return None
    return _deduplicate_tagged(tagged)


def generate_forms(lemma: str, pattern: str | None) -> tuple[str, ...] | None:
    lemma = lemma.strip()
    if not lemma or pattern is None:
        return None
    if pattern in COMMON_PATTERNS:
        forms, _ = _deduplicate_tagged(
            [(lemma, "lemma"), *[(_attach_suffix(lemma, suffix), "derived") for suffix in COMMON_PATTERNS[pattern]]]
        )
        return forms
    explicit = _explicit_pattern_forms(lemma, pattern)
    return explicit[0] if explicit else None


def generate_entry(record: dict[str, Any]) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    if not lemma or pattern is None:
        return None

    if pattern in COMMON_PATTERNS:
        forms, kinds = _deduplicate_tagged(
            [(lemma, "lemma"), *[(_attach_suffix(lemma, suffix), "derived") for suffix in COMMON_PATTERNS[pattern]]]
        )
        group = pattern
    else:
        explicit = _explicit_pattern_forms(lemma, pattern)
        if explicit is None:
            return None
        forms, kinds = explicit
        group = EXPLICIT_PATTERN_GROUP

    return GeneratedEntry(lemma, pattern, forms, group, kinds)


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
    form_kind_counts: Counter[str] = Counter()
    forms: list[str] = []
    seen: set[str] = set()

    for record in read_jsonl(input_path):
        source_records += 1
        entry = generate_entry(record)
        if entry is None:
            continue
        supported_records += 1
        pattern_counts[entry.pattern_group] += 1
        form_kind_counts.update(entry.form_kinds)
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
        "form_kind_counts": dict(form_kind_counts.most_common()),
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
