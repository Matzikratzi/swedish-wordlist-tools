from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _is_hv, _primary_text
from .classify_hv_only import CONTEXT_ONLY, UNKNOWN_WORD, classify_case
from .compare_sources import _is_affix_entry
from .generate_adverb_forms import generated_row as generated_adverb_row
from .generate_numeral_forms import generated_row as generated_numeral_row
from .generate_pronoun_forms import generated_row as generated_pronoun_row
from .generate_real_shared_forms import generated_real_shared_row
from .generate_x_routed_shared_forms import generate_rows as generate_x_rows
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word
from .saol_wordclasses import classes_from_record, record_for_class

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_WORDS = Path("data/processed/saol14-shared-wordlist.txt")
DEFAULT_JSONL = Path("reports/saol14-shared-wordlist.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-shared-wordlist-summary.json")

_LEMMA_ONLY_CLASSES = frozenset({"ADP", "CCONJ", "INTJ", "PROPN", "SCONJ"})
_SHARED_CLASSES = frozenset({"NOUN", "ADJ", "VERB", "PRON", "NUM", "ADV"}) | _LEMMA_ONLY_CLASSES
_OLD_HV_AUDIT_CLASSES = frozenset({"NOUN", "ADJ", "VERB"})
_TEXT_WORD_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü-]+")


def _key(value: str) -> str:
    return value.casefold().strip()


def _lemma(record: dict[str, Any]) -> str:
    return clean_saol_word(record.get("ord")) or clean_saol_word(record.get("normaliserat_ord"))


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _generated_classified_row(record: dict[str, Any], upos: str) -> dict[str, Any] | None:
    class_record = record_for_class(record, upos)
    if upos in _LEMMA_ONLY_CLASSES:
        lemma = _lemma(class_record)
        if not lemma:
            return None
        return {
            "lemma": lemma,
            "forms": [{
                "written_form": lemma,
                "slot": "lemma",
                "provenance": "lemma_only_wordclass",
                "source_token": "",
                "operation_base": lemma,
            }],
        }
    if upos == "PRON":
        return generated_pronoun_row(class_record)
    if upos == "NUM":
        return generated_numeral_row(class_record)
    if upos == "ADV":
        return generated_adverb_row(class_record)
    return generated_real_shared_row(class_record)


def _add_classified_form(
    classified: dict[str, dict[str, Any]],
    written: str,
    upos: str,
    source_id: str,
    provenance: str,
) -> None:
    if (
        not written
        or " " in written
        or written.startswith("-")
        or written.endswith("-")
    ):
        return
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
    if provenance:
        row["provenance"].add(provenance)


def _integrate_routed_x_forms(
    materialized: list[dict[str, Any]],
    classified: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Add structurally routed X/(hv) forms as classified production forms.

    generate_x_rows has already established the target word class from the
    normalized article, explicit homonym reference, printed-form evidence, or
    an unambiguous sibling class. Once that routing is proven, a standalone
    generated form is classified directly. Multiword/context fragments still
    pass through the same structural CONTEXT_ONLY guard as the hv fallback.
    """
    x_rows, _summary = generate_x_rows(materialized)
    source_by_id = {_record_id(record): record for record in materialized if _record_id(record)}
    omitted_context: set[tuple[str, str]] = set()

    for row in x_rows:
        upos = str(row.get("target_upos") or "")
        if upos not in _SHARED_CLASSES:
            continue
        source_id = str(row.get("source_record_id") or "")
        source = source_by_id.get(source_id)
        for form in row.get("forms", []):
            written = clean_saol_word(form.get("written_form"))
            if source is not None and _is_hv(source):
                classification, _reason = classify_case({
                    "form": written,
                    "hv_lemma": clean_saol_word(source.get("normaliserat_ord")),
                })
                if classification == CONTEXT_ONLY:
                    omitted_context.add((source_id, _key(written)))
                    continue
            provenance = str(form.get("provenance") or "x_routed_shared")
            _add_classified_form(classified, written, upos, source_id, provenance)
    return x_rows, len(omitted_context)


def _real_text_word_index(records: Iterable[dict[str, Any]]) -> set[str]:
    words: set[str] = set()
    for record in records:
        if _is_hv(record):
            continue
        text = _primary_text(record)
        if text:
            words.update(token.casefold() for token in _TEXT_WORD_RE.findall(text))
    return words


def _hv_fallback_rows(
    materialized: list[dict[str, Any]],
    classified: dict[str, dict[str, Any]],
    x_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], int, int, int]:
    """Find hv fallbacks while reusing the already generated production forms."""

    explicit_real: set[str] = set()
    hv_records: list[dict[str, Any]] = []
    for record in materialized:
        if _is_hv(record):
            hv_records.append(record)
            continue
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        if printed:
            explicit_real.add(_key(printed))

    mentioned_real = _real_text_word_index(materialized)
    if x_rows is None:
        x_rows, _summary = generate_x_rows(materialized)
    routed_by_source: dict[str, set[str]] = defaultdict(set)
    for row in x_rows:
        source_id = str(row.get("source_record_id") or "")
        for form in row.get("forms", []):
            written = clean_saol_word(form.get("written_form"))
            if written:
                routed_by_source[source_id].add(written)

    unknown_candidates = 0
    context_omitted = 0
    unknown_rows: dict[str, dict[str, Any]] = {}
    seen_candidates: set[str] = set()

    for record in hv_records:
        source_id = _record_id(record)
        forms = set(routed_by_source.get(source_id, set()))
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        if printed:
            forms.add(printed)

        for written in forms:
            if not written or written.startswith("-") or written.endswith("-"):
                continue
            key = _key(written)
            if key in seen_candidates:
                continue
            seen_candidates.add(key)

            if key in classified or key in explicit_real:
                continue
            if " " not in written and key in mentioned_real:
                continue

            classification, _reason = classify_case({
                "form": written,
                "hv_lemma": clean_saol_word(record.get("normaliserat_ord")),
            })
            if classification == CONTEXT_ONLY:
                context_omitted += 1
                continue
            if classification != UNKNOWN_WORD or " " in written:
                continue

            unknown_candidates += 1
            unknown_rows[key] = {
                "form": written,
                "classification": "UNKNOWN_WORD",
                "upos": {"X"},
                "source_record_ids": {source_id} - {""},
                "provenance": {"hv_only_fallback"},
            }

    overlap_keys: set[str] = set()
    for record in hv_records:
        source_id = _record_id(record)
        forms = set(routed_by_source.get(source_id, set()))
        printed = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("stycke"))
        if printed:
            forms.add(printed)
        for written in forms:
            if not written or " " in written or written.startswith("-") or written.endswith("-"):
                continue
            key = _key(written)
            classified_row = classified.get(key)
            if classified_row is None or key in explicit_real or key in mentioned_real:
                continue
            if set(classified_row["upos"]) & _OLD_HV_AUDIT_CLASSES:
                continue
            classification, _reason = classify_case({
                "form": written,
                "hv_lemma": clean_saol_word(record.get("normaliserat_ord")),
            })
            if classification == UNKNOWN_WORD:
                overlap_keys.add(key)

    unknown_suppressed = len(overlap_keys)
    unknown_candidates += unknown_suppressed
    return unknown_rows, unknown_candidates, unknown_suppressed, context_omitted


def build_rows(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    materialized = [dict(record) for record in records]
    classified: dict[str, dict[str, Any]] = {}

    for record in materialized:
        if _is_hv(record):
            continue
        lemma = _lemma(record)
        if not lemma or _is_affix_entry(record, lemma):
            continue
        for upos in classes_from_record(record):
            if upos not in _SHARED_CLASSES:
                continue
            generated = _generated_classified_row(record, upos)
            if generated is None:
                continue
            source_id = _record_id(record)
            for form in generated.get("forms", []):
                written = clean_saol_word(form.get("written_form"))
                provenance = str(form.get("provenance") or form.get("source_stage") or form.get("kind") or "")
                _add_classified_form(classified, written, upos, source_id, provenance)

    x_rows, _routed_context_omitted = _integrate_routed_x_forms(materialized, classified)

    unknown_rows, unknown_candidates, unknown_suppressed, fallback_context_omitted = _hv_fallback_rows(
        materialized, classified, x_rows
    )
    # The fallback pass sees every hv candidate, including context forms already
    # rejected during routed-X integration, so adding both counts would double-count.
    context_omitted = fallback_context_omitted

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
    print(f"Klassificerade former: {summary['classified_forms']}")
    print(f"UNKNOWN_WORD inkluderade: {summary['unknown_forms_included']}")
    print(f"UNKNOWN dubbletter strukna: {summary['unknown_suppressed_by_classified_duplicate']}")
    print(f"CONTEXT_ONLY utelämnade: {summary['context_only_omitted']}")
    print(f"Ordlista: {args.words}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
