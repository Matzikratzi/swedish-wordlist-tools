from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

from .compare_sources import read_saldo
from .export_verb_forms import build_verb_forms
from .jsonl import read_jsonl
from .saldo_verb_fallback import exact_saldo_verb_analyses

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-saldo-verb-overlap.txt")
DEFAULT_JSON = Path("reports/saol14-saldo-verb-overlap.json")
DEFAULT_EXAMPLES = 100


def normalise_playable_word(value: object) -> str | None:
    word = unicodedata.normalize("NFC", str(value or "").strip()).casefold()
    if not word or len(word) < 2 or not word.isalpha():
        return None
    return word


def normalised_words(values: Iterable[object]) -> set[str]:
    result: set[str] = set()
    for value in values:
        word = normalise_playable_word(value)
        if word is not None:
            result.add(word)
    return result


def saldo_forms_for_exact_saol_verbs(
    saol_records: Iterable[Mapping[str, Any]],
    saldo: Mapping[str, list[dict[str, Any]]],
) -> tuple[set[str], int, int]:
    """Return playable raw SALDO forms for exact SAOL verb lemmas.

    Unlike the optional fallback exporter, this function does not remove forms
    already present in SAOL. It is therefore suitable for measuring the true
    intersection between the two sources.
    """
    forms: set[str] = set()
    verb_records = 0
    matched_records = 0
    for record in saol_records:
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        verb_records += 1
        lemma = str(record.get("normaliserat_ord") or "").strip()
        if not lemma:
            continue
        analyses = exact_saldo_verb_analyses(
            lemma,
            saldo.get(lemma.casefold(), ()),
        )
        if not analyses:
            continue
        matched_records += 1
        for analysis in analyses:
            forms.update(normalised_words(analysis.get("forms", ())))
    return forms, verb_records, matched_records


def compare_word_sets(
    saol_words: Iterable[object],
    saldo_words: Iterable[object],
    *,
    example_limit: int = DEFAULT_EXAMPLES,
) -> dict[str, Any]:
    saol = normalised_words(saol_words)
    saldo = normalised_words(saldo_words)
    shared = saol & saldo
    only_saol = saol - saldo
    only_saldo = saldo - saol
    union = saol | saldo

    return {
        "saol_forms": len(saol),
        "saldo_forms": len(saldo),
        "shared_forms": len(shared),
        "only_saol_forms": len(only_saol),
        "only_saldo_forms": len(only_saldo),
        "union_forms": len(union),
        "shared_percent_of_saol": round(100 * len(shared) / len(saol), 2) if saol else 0.0,
        "shared_percent_of_saldo": round(100 * len(shared) / len(saldo), 2) if saldo else 0.0,
        "examples": {
            "shared": sorted(shared)[:example_limit],
            "only_saol": sorted(only_saol)[:example_limit],
            "only_saldo": sorted(only_saldo)[:example_limit],
        },
    }


def build_report(
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
    *,
    example_limit: int = DEFAULT_EXAMPLES,
) -> dict[str, Any]:
    saol_words, export_report = build_verb_forms(saol_path, include_saldo=False)
    records = list(read_jsonl(saol_path))
    saldo = read_saldo(saldo_path)
    saldo_words, verb_records, matched_records = saldo_forms_for_exact_saol_verbs(
        records,
        saldo,
    )
    report = compare_word_sets(
        saol_words,
        saldo_words,
        example_limit=example_limit,
    )
    report.update(
        {
            "saol_path": str(saol_path),
            "saldo_path": str(saldo_path),
            "verb_records": verb_records,
            "exact_saldo_matched_records": matched_records,
            "saol_interpreted_records": export_report["interpreted_records"],
            "note": (
                "SALDO forms are read before fallback deduplication; shared_forms "
                "therefore measures the true normalised source intersection."
            ),
        }
    )
    return report


def render_text(report: Mapping[str, Any]) -> str:
    lines = [
        f"SAOL14 verbposter: {report['verb_records']}",
        f"SAOL14 tolkade poster: {report['saol_interpreted_records']}",
        f"Exakta verbmatchningar i SALDO: {report['exact_saldo_matched_records']}",
        "",
        f"SAOL14-former: {report['saol_forms']}",
        f"SALDO-former för matchade verb: {report['saldo_forms']}",
        f"Gemensamma former: {report['shared_forms']}",
        f"Endast SAOL14: {report['only_saol_forms']}",
        f"Endast SALDO: {report['only_saldo_forms']}",
        f"Union: {report['union_forms']}",
        f"Gemensamma (% av SAOL14): {report['shared_percent_of_saol']:.2f} %",
        f"Gemensamma (% av SALDO): {report['shared_percent_of_saldo']:.2f} %",
    ]
    headings = (
        ("shared", "Exempel: gemensamma"),
        ("only_saol", "Exempel: endast SAOL14"),
        ("only_saldo", "Exempel: endast SALDO"),
    )
    for key, heading in headings:
        lines.extend(["", heading])
        values = report.get("examples", {}).get(key, ())
        lines.extend(f"  {value}" for value in values)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit the true normalised overlap between SAOL14 and raw SALDO verb forms"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--examples", type=int, default=DEFAULT_EXAMPLES)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol, args.saldo, example_limit=max(0, args.examples))
    text = render_text(report)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(text, encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(text, end="")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
