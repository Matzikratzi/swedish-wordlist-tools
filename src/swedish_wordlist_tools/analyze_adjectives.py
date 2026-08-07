from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .adjective_slots import (
    AdjectiveForm,
    AdjectiveSlots,
    interpret_simple_adjective_slots,
)
from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjectives.txt")
DEFAULT_JSON = Path("reports/saol14-adjectives.json")
HARD_CAP = 50
ALPHA_COMPONENT = r"[a-zåäöéü]+"
COMPLETE_HYPHENATED_LEMMA = re.compile(
    rf"{ALPHA_COMPONENT}(?:-{ALPHA_COMPONENT})+",
    re.IGNORECASE,
)
INTENTIONALLY_EXCLUDED_REASONS = frozenset({
    "suffix_or_prefix_lemma",
    "multiword_lemma",
})


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _pattern(text: str) -> str:
    return " ".join(text.split()) if text else "(none)"


def _is_complete_hyphenated_lemma(lemma: str) -> bool:
    return COMPLETE_HYPHENATED_LEMMA.fullmatch(lemma) is not None


def _restore_hyphens(form: str, original_lemma: str) -> str | None:
    parts = original_lemma.split("-")
    boundaries: list[int] = []
    position = 0
    for part in parts[:-1]:
        position += len(part)
        boundaries.append(position)

    if any(boundary > len(form) for boundary in boundaries):
        return None

    restored = form
    for boundary in reversed(boundaries):
        restored = restored[:boundary] + "-" + restored[boundary:]
    return restored


def _interpret_record(record: dict[str, Any]) -> AdjectiveSlots | None:
    slots = interpret_simple_adjective_slots(record)
    if slots is not None:
        return slots

    lemma = _value(record, "normaliserat_ord").casefold()
    if not _is_complete_hyphenated_lemma(lemma):
        return None

    proxy_record = dict(record)
    proxy_record["normaliserat_ord"] = lemma.replace("-", "")
    text = _value(record, "text")
    proxy_record["text"] = text.replace("-", "")
    proxy_slots = interpret_simple_adjective_slots(proxy_record)
    if proxy_slots is None:
        return None

    restored_forms: list[AdjectiveForm] = []
    for form in proxy_slots.forms:
        restored = _restore_hyphens(form.written_form, lemma)
        if restored is None:
            return None
        restored_forms.append(
            AdjectiveForm(restored, form.slot, provenance=form.provenance)
        )

    return AdjectiveSlots(
        lemma=lemma,
        forms=tuple(restored_forms),
        rule=f"hyphenated_{proxy_slots.rule}",
    )


def _remaining_reason(lemma: str, text: str) -> str:
    if not lemma:
        return "missing_lemma"
    if " " in lemma:
        return "multiword_lemma"
    if lemma.startswith("-") or lemma.endswith("-"):
        return "suffix_or_prefix_lemma"
    if not lemma.isalpha() and not _is_complete_hyphenated_lemma(lemma):
        return "nonalpha_lemma"
    if not text:
        return "missing_text"
    lowered = text.casefold()
    if lowered.startswith(("pl.", "best.", "mask.")):
        return "labelled_limited_paradigm"
    if "obrukl." in lowered or "undviks" in lowered or "oböjl." in lowered:
        return "usage_restricted_paradigm"
    if "komp." in lowered or "superl." in lowered:
        return "comparison_or_mixed_pattern"
    return "unparsed_singleword_pattern"


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "ADJ"
    ]
    pattern_counts: Counter[str] = Counter()
    remaining_pattern_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    remaining_reason_counts: Counter[str] = Counter()
    remaining_reason_samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    length_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for record in records:
        lemma = _value(record, "normaliserat_ord")
        text = _value(record, "text")
        stycke = _value(record, "stycke")
        pattern = _pattern(text)
        slots = _interpret_record(record)
        pattern_counts[pattern] += 1
        reason = None
        if slots is None:
            remaining_pattern_counts[pattern] += 1
            reason = _remaining_reason(lemma, text)
            remaining_reason_counts[reason] += 1
            if len(remaining_reason_samples[reason]) < 30:
                remaining_reason_samples[reason].append({
                    "lemma": lemma,
                    "homonr": _value(record, "homonr"),
                    "text": text or "(none)",
                })
        else:
            rule_counts[slots.rule] += 1
        length_counts["at_hard_cap" if len(text) == HARD_CAP else "below_hard_cap"] += 1
        rows.append({
            "lemma": lemma,
            "homonr": _value(record, "homonr"),
            "text": text or None,
            "text_length": len(text),
            "at_hard_cap": len(text) == HARD_CAP,
            "has_bar": "|" in stycke,
            "stycke": stycke,
            "ordkl": _value(record, "ordkl"),
            "interpreted": slots is not None,
            "remaining_reason": reason,
            "intentionally_excluded": reason in INTENTIONALLY_EXCLUDED_REASONS,
            "rule": slots.rule if slots else None,
            "forms": list(slots.written_forms()) if slots else [],
            "source": _value(record, "source"),
        })

    interpreted = sum(1 for row in rows if row["interpreted"])
    intentionally_excluded = sum(1 for row in rows if row["intentionally_excluded"])
    unresolved = len(records) - interpreted - intentionally_excluded
    rows.sort(key=lambda row: (not row["at_hard_cap"], row["interpreted"], row["lemma"], row["homonr"]))
    excluded_counts = {
        reason: count
        for reason, count in remaining_reason_counts.items()
        if reason in INTENTIONALLY_EXCLUDED_REASONS
    }
    unresolved_counts = {
        reason: count
        for reason, count in remaining_reason_counts.items()
        if reason not in INTENTIONALLY_EXCLUDED_REASONS
    }
    return {
        "adjective_records": len(records),
        "with_text": sum(1 for row in rows if row["text"]),
        "without_text": sum(1 for row in rows if not row["text"]),
        "interpreted_simple_records": interpreted,
        "interpreted_simple_percent": round(100 * interpreted / len(records), 2) if records else 0.0,
        "remaining_records": len(records) - interpreted,
        "intentionally_excluded_records": intentionally_excluded,
        "unresolved_records": unresolved,
        "intentionally_excluded_reason_counts": dict(Counter(excluded_counts).most_common()),
        "unresolved_reason_counts": dict(Counter(unresolved_counts).most_common()),
        "at_hard_cap": length_counts["at_hard_cap"],
        "with_bar": sum(1 for row in rows if row["has_bar"]),
        "unique_raw_patterns": len(pattern_counts),
        "rule_counts": dict(rule_counts.most_common()),
        "remaining_reason_counts": dict(remaining_reason_counts.most_common()),
        "remaining_reason_samples": dict(remaining_reason_samples),
        "top_raw_patterns": pattern_counts.most_common(100),
        "top_remaining_patterns": remaining_pattern_counts.most_common(100),
        "records": rows,
        "note": (
            "Leading-hyphen suffix entries and lemmas containing spaces are intentionally "
            "excluded from the playable word list. unresolved_records counts only genuine "
            "single-word parsing gaps."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Adjektivposter: {report['adjective_records']}",
        f"Med text: {report['with_text']}",
        f"Utan text: {report['without_text']}",
        f"Tolkade spelbara poster: {report['interpreted_simple_records']} "
        f"({report['interpreted_simple_percent']:.2f} %)",
        f"Avsiktligt exkluderade poster: {report['intentionally_excluded_records']}",
        f"Verkligt otolkade poster: {report['unresolved_records']}",
        f"Vid 50-teckensgränsen: {report['at_hard_cap']}",
        f"Med lodstreck i stycke: {report['with_bar']}",
        f"Unika råa textmönster: {report['unique_raw_patterns']}",
        "",
        "Avsiktligt exkluderade:",
    ]
    for reason, count in report["intentionally_excluded_reason_counts"].items():
        lines.append(f"  {count:6d}  {reason}")
    lines.extend(["", "Verkligt otolkade:"])
    if not report["unresolved_reason_counts"]:
        lines.append("  (inga)")
    for reason, count in report["unresolved_reason_counts"].items():
        lines.append(f"  {count:6d}  {reason}")

    lines.extend(["", "Tolkade regler:"])
    for rule, count in report["rule_counts"].items():
        lines.append(f"  {count:6d}  {rule}")

    lines.extend(["", "Exempel per exkluderad/återstående orsak:"])
    for reason, samples in report["remaining_reason_samples"].items():
        lines.append(f"  {reason}:")
        for row in samples[:12]:
            lines.append(
                f"    {row['lemma']} (homonr={row['homonr'] or '-'}) | text={row['text']!r}"
            )

    lines.extend(["", "Poster vid 50-teckensgränsen:"])
    capped = [row for row in report["records"] if row["at_hard_cap"]]
    if not capped:
        lines.append("  (inga)")
    for row in capped[:300]:
        lines.append(
            f"  {row['lemma']} (homonr={row['homonr'] or '-'}) | "
            f"text={row['text']!r} | stycke={row['stycke']!r}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory and conservatively parse SAOL14 adjective rows")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Adjektivposter: {report['adjective_records']}")
    print(f"Tolkade spelbara poster: {report['interpreted_simple_records']}")
    print(f"Avsiktligt exkluderade poster: {report['intentionally_excluded_records']}")
    print(f"Verkligt otolkade poster: {report['unresolved_records']}")
    for reason, count in report["unresolved_reason_counts"].items():
        print(f"{reason}: {count}")
    print(f"Vid 50-teckensgränsen: {report['at_hard_cap']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
