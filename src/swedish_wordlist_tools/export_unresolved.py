from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_AMBIGUOUS = Path("reports/saol14-saldo-ambiguous.jsonl")
DEFAULT_COMPOUNDS = Path("reports/saol14-compound-heads.jsonl")
DEFAULT_OUTPUT = Path("reports/saol14-unresolved.jsonl")

SOLVED_COMPOUND_REASONS = {"unique_head_same_upos"}


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _record_id(row: dict[str, Any]) -> str:
    return str(row.get("record_id") or row.get("id") or row.get("subnr") or "")


def _lemma(row: dict[str, Any]) -> str:
    return _normalise(str(row.get("lemma") or row.get("normaliserat_ord") or ""))


def unresolved_selectors(
    ambiguous_rows: Iterable[dict[str, Any]],
    compound_rows: Iterable[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    record_ids: set[str] = set()
    fallback_lemmas: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        record_id = _record_id(row)
        if record_id:
            record_ids.add(record_id)
        else:
            lemma = _lemma(row)
            if lemma:
                fallback_lemmas.add(lemma)

    for row in ambiguous_rows:
        add(row)
    for row in compound_rows:
        if str(row.get("head_match_reason", "")) not in SOLVED_COMPOUND_REASONS:
            add(row)

    return record_ids, fallback_lemmas


def filter_unresolved(
    saol_rows: Iterable[dict[str, Any]],
    record_ids: set[str],
    fallback_lemmas: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in saol_rows:
        record_id = _record_id(row)
        if record_id:
            if record_id in record_ids:
                rows.append(row)
        elif _lemma(row) in fallback_lemmas:
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def export_unresolved(
    saol_path: Path = DEFAULT_SAOL,
    ambiguous_path: Path = DEFAULT_AMBIGUOUS,
    compounds_path: Path = DEFAULT_COMPOUNDS,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    record_ids, fallback_lemmas = unresolved_selectors(
        read_jsonl(ambiguous_path),
        read_jsonl(compounds_path),
    )
    rows = filter_unresolved(read_jsonl(saol_path), record_ids, fallback_lemmas)
    write_jsonl(output_path, rows)
    return {
        "records": len(rows),
        "record_id_selectors": len(record_ids),
        "fallback_lemma_selectors": len(fallback_lemmas),
        "output": str(output_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write the original SAOL 14 JSONL with already handled records removed"
    )
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--ambiguous", type=Path, default=DEFAULT_AMBIGUOUS)
    parser.add_argument("--compounds", type=Path, default=DEFAULT_COMPOUNDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = export_unresolved(
        args.saol,
        args.ambiguous,
        args.compounds,
        args.output,
    )
    print(f"Olösta SAOL-poster: {summary['records']}")
    print(f"JSONL: {summary['output']}")


if __name__ == "__main__":
    main()
