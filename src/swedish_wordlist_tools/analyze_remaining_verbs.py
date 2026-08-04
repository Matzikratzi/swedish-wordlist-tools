from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .inflect import normalise_pattern
from .jsonl import read_jsonl
from .verb_compound_heads import build_simple_verb_paradigm_index
from .verb_slots import diagnose_verb_record, interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-verbs.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-verbs.json")
TEXT_HARD_CAP = 50


def _clean_stycke(value: object) -> str:
    text = str(value or "")
    # The compound-head code owns the actual interpretation. Here we only need
    # a readable marker for the focused report.
    return text


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = [
        record
        for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "VERB"
    ]
    interpreted = {id(record): interpret_verb_slots(record) for record in records}
    head_index = build_simple_verb_paradigm_index(records, interpreted)

    remaining: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    hard_cap_counts: Counter[str] = Counter()
    bar_counts: Counter[str] = Counter()

    for record in records:
        if interpreted[id(record)] is not None:
            continue

        lemma = str(record.get("normaliserat_ord") or "").strip()
        raw_text = str(record.get("text") or "")
        pattern = normalise_pattern(record.get("text")) or "(none)"
        reason = diagnose_verb_record(record)
        at_hard_cap = len(raw_text) == TEXT_HARD_CAP
        stycke = _clean_stycke(record.get("stycke"))
        has_bar = "|" in stycke

        # Exact compound heads are indexed by the same production helper used
        # by the repair stage. Do not guess a head from the written lemma here.
        head_key = ""
        if has_bar:
            right = stycke.rsplit("|", 1)[-1]
            # Remove the visual syllable marker used in SAOL facsimile text.
            head_key = right.replace("·", "").strip().casefold()
        head_slots = head_index.get(head_key) if head_key else None
        recoverable_from_head = head_slots is not None

        reason_counts[reason] += 1
        pattern_counts[pattern] += 1
        hard_cap_counts["at_hard_cap" if at_hard_cap else "below_hard_cap"] += 1
        if has_bar:
            bar_counts["bar_marked"] += 1
            bar_counts[
                "exact_head_found" if recoverable_from_head else "exact_head_missing"
            ] += 1
        else:
            bar_counts["without_bar"] += 1

        remaining.append(
            {
                "lemma": lemma,
                "reason": reason,
                "pattern": pattern,
                "raw_text": raw_text,
                "text_length": len(raw_text),
                "at_hard_cap": at_hard_cap,
                "stycke": stycke,
                "bar_marked": has_bar,
                "head_key": head_key,
                "exact_head_found": recoverable_from_head,
                "head_slots": list(head_slots.slots()) if head_slots is not None else [],
                "ordkl": str(record.get("ordkl") or ""),
                "source": str(record.get("source") or ""),
            }
        )

    remaining.sort(key=lambda row: (row["reason"], row["pattern"], row["lemma"]))
    return {
        "verb_records": len(records),
        "interpreted_records": len(records) - len(remaining),
        "remaining_records": len(remaining),
        "coverage_percent": round(
            100 * (len(records) - len(remaining)) / len(records), 2
        ) if records else 0.0,
        "reason_counts": dict(reason_counts.most_common()),
        "hard_cap_counts": dict(hard_cap_counts.most_common()),
        "compound_head_counts": dict(bar_counts.most_common()),
        "largest_patterns": dict(pattern_counts.most_common(100)),
        "records": remaining,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Tolkade: {report['interpreted_records']}",
        f"Kvar: {report['remaining_records']}",
        f"Täckning: {report['coverage_percent']:.2f} %",
        "",
        "Orsaker:",
    ]
    for reason, count in report["reason_counts"].items():
        lines.append(f"  {count:5d}  {reason}")

    lines.extend(["", "50-teckensgränsen:"])
    for key, count in report["hard_cap_counts"].items():
        lines.append(f"  {count:5d}  {key}")

    lines.extend(["", "Lodstreck och exakt huvudverb:"])
    for key, count in report["compound_head_counts"].items():
        lines.append(f"  {count:5d}  {key}")

    lines.extend(["", "Största återstående mönster:"])
    for pattern, count in report["largest_patterns"].items():
        lines.append(f"  {count:5d}  {pattern}")

    lines.extend(["", "Alla återstående poster:"])
    for row in report["records"]:
        head = ""
        if row["bar_marked"]:
            status = "head=found" if row["exact_head_found"] else "head=missing"
            head = f" | {status}:{row['head_key']}"
        lines.append(
            f"  {row['lemma']} | {row['reason']} | len={row['text_length']}"
            f" | stycke={row['stycke']!r}{head} | {row['pattern']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse only the SAOL14 verb records not handled by the row interpreter"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    text = render_text(report)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(text, encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Verbposter: {report['verb_records']}")
    print(f"Tolkade: {report['interpreted_records']}")
    print(f"Kvar: {report['remaining_records']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
