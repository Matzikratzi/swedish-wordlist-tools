from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .inflect import generate_entry, normalise_pattern
from .jsonl import read_jsonl
from .noun_paradigm import complete_noun_entry
from .saol_row_interpreter import interpret_noun_row

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-row-interpreter.txt")
DEFAULT_JSON = Path("reports/saol14-row-interpreter.json")

_HYPHENS = "‐‑‒–—−﹘﹣－"
_HYPHEN_TRANSLATION = str.maketrans({char: "-" for char in _HYPHENS})


def _old_key_forms(record: dict[str, Any]) -> dict[str, str]:
    entry = complete_noun_entry(record, generate_entry(record))
    if entry is None:
        return {}
    result: dict[str, str] = {}
    for word_form in entry.word_forms:
        if word_form.msd is None:
            continue
        msd = str(word_form.msd).casefold()
        if msd == "ci":
            result.setdefault("lemma", word_form.written_form)
        elif msd == "sg def nom":
            result.setdefault("sg_def", word_form.written_form)
        elif msd == "pl indef nom":
            result.setdefault("pl_indef", word_form.written_form)
        elif msd == "pl def nom":
            result.setdefault("pl_def", word_form.written_form)
    return result


def _comparison_spelling(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.translate(_HYPHEN_TRANSLATION)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return text.casefold().strip()


def _unsupported_reason(record: dict[str, Any], pattern: str) -> str:
    if pattern == "(none)":
        return "missing_pattern"
    if "-" not in pattern:
        return "unsupported_syntax"

    stycke = str(record.get("stycke", "") or "").strip()
    if "|" not in stycke:
        return "minus_form_without_bar"
    if _comparison_spelling(stycke) != _comparison_spelling(record.get("normaliserat_ord")):
        return "bar_marked_stycke_does_not_match_lemma"
    return "minus_form_not_applied"


def build_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    noun_records = 0
    interpreted = 0
    same_shared_slots = 0
    differences: Counter[str] = Counter()
    unsupported_patterns: Counter[str] = Counter()
    unsupported_reasons: Counter[str] = Counter()
    unsupported_examples: dict[str, list[dict[str, Any]]] = {}
    examples: list[dict[str, Any]] = []

    for record in records:
        if str(record.get("upos", "")).upper() != "NOUN":
            continue
        noun_records += 1
        new = interpret_noun_row(record)
        pattern = normalise_pattern(record.get("text")) or "(none)"
        if new is None:
            unsupported_patterns[pattern] += 1
            reason = _unsupported_reason(record, pattern)
            unsupported_reasons[reason] += 1
            reason_examples = unsupported_examples.setdefault(reason, [])
            if len(reason_examples) < 30:
                reason_examples.append(
                    {
                        "lemma": record.get("normaliserat_ord"),
                        "stycke": record.get("stycke"),
                        "ordkl": record.get("ordkl"),
                        "raw_text": record.get("text"),
                        "pattern": pattern,
                    }
                )
            continue
        interpreted += 1
        new_forms = {form.slot: form.written_form for form in new.key_forms}
        old_forms = _old_key_forms(record)
        shared = sorted(set(new_forms) & set(old_forms))
        mismatched = [slot for slot in shared if new_forms[slot] != old_forms[slot]]
        if not mismatched:
            same_shared_slots += 1
            continue
        for slot in mismatched:
            differences[slot] += 1
        if len(examples) < 50:
            examples.append(
                {
                    "lemma": record.get("normaliserat_ord"),
                    "stycke": record.get("stycke"),
                    "pattern": pattern,
                    "new": new_forms,
                    "old": old_forms,
                    "mismatched_slots": mismatched,
                }
            )

    return {
        "noun_records": noun_records,
        "interpreted": interpreted,
        "coverage_percent": round(100 * interpreted / noun_records, 2) if noun_records else 0.0,
        "same_shared_slots": same_shared_slots,
        "different_shared_slots": interpreted - same_shared_slots,
        "difference_slots": dict(differences.most_common()),
        "unsupported_reasons": dict(unsupported_reasons.most_common()),
        "unsupported_examples": unsupported_examples,
        "largest_unsupported_patterns": dict(unsupported_patterns.most_common(50)),
        "difference_examples": examples,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Substantivposter: {report['noun_records']}",
        f"Tolkade rad för rad: {report['interpreted']}",
        f"Täckning: {report['coverage_percent']:.2f} %",
        f"Samma i alla gemensamma slots: {report['same_shared_slots']}",
        f"Skillnad i gemensam slot: {report['different_shared_slots']}",
        "",
        "Skillnader per slot:",
    ]
    for slot, count in report["difference_slots"].items():
        lines.append(f"  {count:6d}  {slot}")

    lines.extend(["", "Orsaker till otolkade rader:"])
    for reason, count in report["unsupported_reasons"].items():
        lines.append(f"  {count:6d}  {reason}")

    missing_rows = report["unsupported_examples"].get("missing_pattern", [])
    if missing_rows:
        lines.extend(["", "Exempel på poster utan böjningsmönster:"])
        for row in missing_rows[:30]:
            lines.append(
                "    "
                f"{row.get('lemma')!s} | stycke={row.get('stycke')!r} "
                f"| ordkl={row.get('ordkl')!r} | raw_text={row.get('raw_text')!r}"
            )

    lines.extend(["", "Exempel på otolkade minusformer:"])
    for reason in (
        "minus_form_without_bar",
        "bar_marked_stycke_does_not_match_lemma",
        "minus_form_not_applied",
    ):
        rows = report["unsupported_examples"].get(reason, [])
        if not rows:
            continue
        lines.append(f"  {reason}:")
        for row in rows[:20]:
            lines.append(
                f"    {row.get('lemma')!s} | stycke={row.get('stycke')!r} | {row.get('pattern')!s}"
            )

    lines.extend(["", "Största ännu otolkade mönster:"])
    for pattern, count in report["largest_unsupported_patterns"].items():
        lines.append(f"  {count:6d}  {pattern}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare the generic row interpreter with the current noun pipeline"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Substantivposter: {report['noun_records']}")
    print(f"Tolkade: {report['interpreted']}")
    print(f"Täckning: {report['coverage_percent']:.2f} %")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
