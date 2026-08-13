from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _is_hv
from .classify_hv_only import CONTEXT_ONLY, UNKNOWN_WORD, analyze as classify_hv_only
from .compare_sources import _saol_upos
from .generate_numeral_forms import generated_row as generated_numeral_row
from .generate_pronoun_forms import generated_row as generated_pronoun_row
from .generate_real_shared_forms import generated_real_shared_row
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_WORDS = Path("data/processed/saol14-shared-wordlist.txt")
DEFAULT_JSONL = Path("reports/saol14-shared-wordlist.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-shared-wordlist-summary.json")

_SHARED_CLASSES = frozenset({"NOUN", "ADJ", "VERB", "PRON", "NUM"})


def _key(value: str) -> str:
    return value.casefold().strip()


def _generated_classified_row(record: dict[str, Any], upos: str) -> dict[str, Any] | None:
    if upos == "PRON":
        return generated_pronoun_row(record)
    if upos == "NUM":
        return generated_numeral_row(record)
    return generated_real_shared_row(record)


def build_rows(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the current production word set from verified shared classes.

    Classified forms from real NOUN/ADJ/VERB/PRON/NUM rows have authority.
    Forms that survive only via an (hv) row are included as UNKNOWN_WORD only
    when no classified form with the same written spelling exists.
    CONTEXT_ONLY rows never enter the word list.
    """

    materialized = [dict(record) for record in records]
    classified: dict[str, dict[str, Any]] = {}

    for record in materialized:
        if _is_hv(record):
            continue
        upos = _saol_upos(record)
        if upos not in _SHARED_CLASSES:
            continue
        generated = _generated_classified_row(record, upos)
        if generated is None:
            continue
        source_id = str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")
        for form in generated.get("forms", []):
            written = clean_saol_word(form.get("written_form"))
            if not written or " " in written:
                continue
            key = _key(written)
            row = classified.setdefault(key, {
                "form": written,
                "classification": "CLASSIFIED",
                "upos": set(),
                "source_record_ids": set(),
                "provenance": set(),
            })
            row["upos"].add(upos)
            if source_id:
                row["source_record_ids"].add(source_id)
            provenance = str(form.get("provenance") or form.get("source_stage") or form.get("kind") or "")
            if provenance:
                row["provenance"].add(provenance)

    hv_report = classify_hv_only(materialized)
    unknown_candidates = 0
    unknown_suppressed = 0
    context_omitted = 0
    unknown_rows: dict[str, dict[str, Any]] = {}
    for row in hv_report["rows"]:
        classification = row["classification"]
        written = clean_saol_word(row.get("form"))
        if not written or " " in written:
            if classification == CONTEXT_ONLY:
                context_omitted += 1
            continue
        key = _key(written)
        if classification == CONTEXT_ONLY:
            context_omitted += 1
            continue
        if classification != UNKNOWN_WORD:
            continue
        unknown_candidates += 1
        if key in classified:
            unknown_suppressed += 1
            continue
        unknown_rows.setdefault(key, {
            "form": written,
            "classification": "UNKNOWN_WORD",
            "upos": {"X"},
            "source_record_ids": {str(row.get("hv_record_id") or "")} - {""},
            "provenance": {"hv_only_fallback"},
        })

    rows: list[dict[str, Any]] = []
    for row in (*classified.values(), *unknown_rows.values()):
        rows.append({
            "form": row["form"],
            "classification": row["classification"],
            "upos": sorted(row["upos"]),
            "source_record_ids": sorted(row["source_record_ids"]),
            "provenance": sorted(row["provenance"]),
        })
    rows.sort(key=lambda row: _key(str(row["form"])))

    counts = Counter(str(row["classification"]) for row in rows)
    summary = {
        "unique_forms": len(rows),
        "classified_forms": counts.get("CLASSIFIED", 0),
        "unknown_forms_included": counts.get("UNKNOWN_WORD", 0),
        "unknown_candidates": unknown_candidates,
        "unknown_suppressed_by_classified_duplicate": unknown_suppressed,
        "context_only_omitted": context_omitted,
        "classes": sorted(_SHARED_CLASSES),
    }
    return rows, summary


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], words_path: Path, jsonl_path: Path, summary_path: Path) -> None:
    words_path.parent.mkdir(parents=True, exist_ok=True)
    words_path.write_text("\n".join(str(row["form"]) for row in rows) + "\n", encoding="utf-8")

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build current SAOL shared-class word list with low-priority hv UNKNOWN fallback")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--words", type=Path, default=DEFAULT_WORDS)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows, summary = build_rows(read_jsonl(args.source))
    write_outputs(rows, summary, args.words, args.jsonl, args.summary)
    print(f"Unika ordformer: {summary['unique_forms']}")
    print(f"Klassificerade NOUN/ADJ/VERB/PRON/NUM-former: {summary['classified_forms']}")
    print(f"UNKNOWN_WORD inkluderade: {summary['unknown_forms_included']}")
    print(f"UNKNOWN dubbletter strukna: {summary['unknown_suppressed_by_classified_duplicate']}")
    print(f"CONTEXT_ONLY utelämnade: {summary['context_only_omitted']}")
    print(f"Ordlista: {args.words}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
