from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyze_verb_notation_inventory import DEFAULT_SAOL
from .jsonl import read_jsonl
from .verb_game_fallback import interpret_playable_verb_slots
from .verb_shared_lexeme import interpret_shared_playable_verb_slots

DEFAULT_TEXT = Path("reports/saol14-verb-shared-delta.txt")
DEFAULT_JSON = Path("reports/saol14-verb-shared-delta.json")


def _forms(slots: Any) -> set[str]:
    if slots is None:
        return set()
    return {str(value) for value in slots.written_forms() if str(value)}


def _is_direct_playable_verb(record: dict[str, Any]) -> bool:
    if str(record.get("upos") or "").upper() != "VERB":
        return False
    lemma = str(record.get("normaliserat_ord") or "").strip()
    return bool(lemma and " " not in lemma and not lemma.startswith("-") and not lemma.endswith("-"))


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    old_words: set[str] = set()
    shared_words: set[str] = set()
    changed: list[dict[str, Any]] = []

    for record in records:
        if not _is_direct_playable_verb(record):
            continue
        counts["records"] += 1
        old = interpret_playable_verb_slots(record)
        shared = interpret_shared_playable_verb_slots(record)
        old_forms = _forms(old)
        shared_forms = _forms(shared)
        old_words.update(old_forms)
        shared_words.update(shared_forms)

        if old is not None:
            counts["old_interpreted"] += 1
        if shared is not None:
            counts["shared_interpreted"] += 1

        old_only = sorted(old_forms - shared_forms, key=str.casefold)
        shared_only = sorted(shared_forms - old_forms, key=str.casefold)
        if not old_only and not shared_only:
            counts["same_records"] += 1
            continue

        counts["changed_records"] += 1
        changed.append(
            {
                "lemma": str(record.get("normaliserat_ord") or ""),
                "homonym_number": str(record.get("homonr") or ""),
                "text": str(record.get("text") or ""),
                "record_id": str(record.get("id") or record.get("subnr") or ""),
                "old_only": old_only,
                "shared_only": shared_only,
                "old_forms": sorted(old_forms, key=str.casefold),
                "shared_forms": sorted(shared_forms, key=str.casefold),
                "source_truncated": bool(shared and shared.metadata.get("source_truncated") == "true"),
            }
        )

    changed.sort(key=lambda row: (row["lemma"].casefold(), row["homonym_number"], row["record_id"]))
    old_only_words = sorted(old_words - shared_words, key=str.casefold)
    shared_only_words = sorted(shared_words - old_words, key=str.casefold)
    return {
        "records": counts["records"],
        "old_interpreted": counts["old_interpreted"],
        "shared_interpreted": counts["shared_interpreted"],
        "same_records": counts["same_records"],
        "changed_records": counts["changed_records"],
        "old_unique_forms": len(old_words),
        "shared_unique_forms": len(shared_words),
        "old_only_unique_forms": len(old_only_words),
        "shared_only_unique_forms": len(shared_only_words),
        "old_only_words": old_only_words,
        "shared_only_words": shared_only_words,
        "changed": changed,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 VERB: shared radtolkning jämförd med nuvarande verbväg",
        "",
        "Endast direkt spelbara enkelordslemma jämförs. Compound-head-borrowing,",
        "SALDO-fallback och andra efterföljande expansionssteg ingår inte.",
        "",
        f"Poster: {summary['records']}",
        f"Nuvarande väg tolkar: {summary['old_interpreted']}",
        f"Shared-vägen tolkar: {summary['shared_interpreted']}",
        f"Poster med identiska ordformer: {summary['same_records']}",
        f"Poster med ändrad output: {summary['changed_records']}",
        f"Unika former nuvarande: {summary['old_unique_forms']}",
        f"Unika former shared: {summary['shared_unique_forms']}",
        f"Unika former endast nuvarande: {summary['old_only_unique_forms']}",
        f"Unika former endast shared: {summary['shared_only_unique_forms']}",
        "",
        "Ändrade poster:",
    ]
    if not summary["changed"]:
        lines.append("  (inga)")
        return "\n".join(lines) + "\n"
    for row in summary["changed"]:
        hom = f" ({row['homonym_number']})" if row["homonym_number"] else ""
        trunc = " | TRUNKERAD" if row["source_truncated"] else ""
        lines.append(f"  {row['lemma']}{hom}{trunc} | {row['text']}")
        if row["old_only"]:
            lines.append("    endast nuvarande: " + ", ".join(row["old_only"]))
        if row["shared_only"]:
            lines.append("    endast shared: " + ", ".join(row["shared_only"]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jämför shared verbtolkning med nuvarande radtolkning")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze(list(read_jsonl(args.saol)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Poster: {summary['records']}")
    print(f"Nuvarande väg tolkar: {summary['old_interpreted']}")
    print(f"Shared-vägen tolkar: {summary['shared_interpreted']}")
    print(f"Poster med identiska ordformer: {summary['same_records']}")
    print(f"Poster med ändrad output: {summary['changed_records']}")
    print(f"Unika former nuvarande: {summary['old_unique_forms']}")
    print(f"Unika former shared: {summary['shared_unique_forms']}")
    print(f"Endast nuvarande: {summary['old_only_unique_forms']}")
    print(f"Endast shared: {summary['shared_only_unique_forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
