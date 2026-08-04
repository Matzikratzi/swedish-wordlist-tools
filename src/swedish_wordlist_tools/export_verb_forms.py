from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import read_saldo
from .jsonl import read_jsonl
from .saldo_verb_fallback import add_saldo_attested_forms
from .verb_compound_heads import borrow_compound_verb_slots, build_simple_verb_paradigm_index
from .verb_game_fallback import interpret_playable_verb_slots
from .verb_slot_schema import add_explicit_verb_row_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_OUTPUT = Path("data/processed/saol14-verb-forms.txt")
DEFAULT_REPORT = Path("reports/saol14-verb-forms.json")


def _normalise_word(value: str) -> str | None:
    word = value.strip().casefold()
    if not word or len(word) < 2 or not word.isalpha():
        return None
    return word


def build_verb_forms(
    saol_path: Path = DEFAULT_SAOL,
    *,
    include_saldo: bool = False,
    saldo_path: Path = DEFAULT_SALDO,
) -> tuple[list[str], dict[str, Any]]:
    records = [
        record
        for record in read_jsonl(saol_path)
        if str(record.get("upos", "")).upper() == "VERB"
    ]
    interpreted = {
        id(record): (
            add_explicit_verb_row_slots(record, slots)
            if (slots := interpret_playable_verb_slots(record)) is not None
            else None
        )
        for record in records
    }
    head_index = build_simple_verb_paradigm_index(records, interpreted)
    saldo = read_saldo(saldo_path) if include_saldo else {}

    words: set[str] = set()
    provenance_words: dict[str, set[str]] = {}
    record_counts: Counter[str] = Counter()

    for record in records:
        slots = interpreted[id(record)]
        slots = borrow_compound_verb_slots(record, head_index, slots)
        if slots is None:
            continue
        if include_saldo:
            slots = add_saldo_attested_forms(
                slots,
                saldo.get(slots.lemma.casefold(), ()),
            )

        record_counts["interpreted"] += 1
        for form in slots.forms:
            word = _normalise_word(form.written_form)
            if word is None:
                continue
            words.add(word)
            provenance_words.setdefault(form.provenance, set()).add(word)

    ordered = sorted(words)
    report: dict[str, Any] = {
        "source": "SAOL14+SALDO" if include_saldo else "SAOL14",
        "include_saldo": include_saldo,
        "verb_records": len(records),
        "interpreted_records": record_counts["interpreted"],
        "unique_playable_forms": len(ordered),
        "unique_forms_by_provenance": {
            source: len(values)
            for source, values in sorted(provenance_words.items())
        },
    }
    if include_saldo:
        saol_words = set().union(
            *(values for source, values in provenance_words.items() if source != "saldo")
        ) if any(source != "saldo" for source in provenance_words) else set()
        saldo_words = provenance_words.get("saldo", set())
        report["saldo_only_unique_forms"] = len(saldo_words - saol_words)
        report["saldo_forms_already_in_saol"] = len(saldo_words & saol_words)
    return ordered, report


def write_export(
    words: Iterable[str],
    report: dict[str, Any],
    output_path: Path,
    report_path: Path,
) -> None:
    values = list(words)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(values) + ("\n" if values else ""), encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export playable verb forms; SAOL14 only by default"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--include-saldo", action="store_true")
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    words, report = build_verb_forms(
        args.saol,
        include_saldo=args.include_saldo,
        saldo_path=args.saldo,
    )
    write_export(words, report, args.output, args.report)
    print(f"Källa: {report['source']}")
    print(f"Verbposter: {report['verb_records']}")
    print(f"Tolkade poster: {report['interpreted_records']}")
    print(f"Unika spelbara verbformer: {report['unique_playable_forms']}")
    if args.include_saldo:
        print(f"Endast från SALDO: {report['saldo_only_unique_forms']}")
    print(f"Utdata: {args.output}")
    print(f"Rapport: {args.report}")


if __name__ == "__main__":
    main()
