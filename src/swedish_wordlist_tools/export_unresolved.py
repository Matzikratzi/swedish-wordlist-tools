from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SAOL_ONLY = Path("reports/saol14-only.jsonl")
DEFAULT_AMBIGUOUS = Path("reports/saol14-saldo-ambiguous.jsonl")
DEFAULT_COMPOUNDS = Path("reports/saol14-compound-heads.jsonl")
DEFAULT_COMPARISON = Path("reports/saol14-saldo-comparison.json")
DEFAULT_OUTPUT = Path("reports/saol14-unresolved.jsonl")

SOLVED_COMPOUND_REASON = "unique_head_same_upos"

Selector = tuple[str, str, str, str, str, str, str]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _selector(row: dict[str, Any]) -> Selector | None:
    """Build the same stable record key from source and generated report rows.

    ``record_id``/``subnr`` is not unique in the SAOL source. Include the lemma,
    homonym number, word classes, notation, and source to distinguish records.
    A Counter is still used because completely identical records may occur more
    than once and must not be collapsed.
    """
    record_id = str(row.get("record_id") or row.get("id") or row.get("subnr") or "")
    lemma = _normalise(str(row.get("lemma") or row.get("normaliserat_ord") or ""))
    homonym = str(row.get("homonym_number") or row.get("homonr") or "")
    source_upos = _normalise(str(row.get("source_upos") or row.get("upos") or ""))
    ordkl = _normalise(str(row.get("ordkl") or ""))
    notation = _normalise(str(row.get("notation") or row.get("text") or ""))
    source = _normalise(str(row.get("source") or ""))
    if not any((record_id, lemma, homonym, source_upos, ordkl, notation, source)):
        return None
    return record_id, lemma, homonym, source_upos, ordkl, notation, source


def selector_counts(rows: Iterable[dict[str, Any]]) -> Counter[Selector]:
    result: Counter[Selector] = Counter()
    for row in rows:
        selector = _selector(row)
        if selector is not None:
            result[selector] += 1
    return result


def solved_compound_counts(rows: Iterable[dict[str, Any]]) -> Counter[Selector]:
    return selector_counts(
        row
        for row in rows
        if str(row.get("head_match_reason", "")) == SOLVED_COMPOUND_REASON
    )


def subtract_counts(
    baseline: Counter[Selector], solved: Counter[Selector]
) -> tuple[Counter[Selector], int]:
    remaining = baseline.copy()
    removed = 0
    for selector, count in solved.items():
        matched = min(count, remaining[selector])
        if matched:
            remaining[selector] -= matched
            removed += matched
            if remaining[selector] == 0:
                del remaining[selector]
    return remaining, removed


def filter_by_counts(
    saol_rows: Iterable[dict[str, Any]], wanted: Counter[Selector]
) -> list[dict[str, Any]]:
    remaining = wanted.copy()
    result: list[dict[str, Any]] = []
    for row in saol_rows:
        selector = _selector(row)
        if selector is not None and remaining[selector] > 0:
            result.append(row)
            remaining[selector] -= 1
            if remaining[selector] == 0:
                del remaining[selector]
    if remaining:
        missing = sum(remaining.values())
        raise RuntimeError(
            f"Kunde inte hitta {missing} olösta rapportposter i SAOL-originalet. Ingen fil skrevs."
        )
    return result


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def export_unresolved(
    saol_path: Path = DEFAULT_SAOL,
    saol_only_path: Path = DEFAULT_SAOL_ONLY,
    ambiguous_path: Path = DEFAULT_AMBIGUOUS,
    compounds_path: Path = DEFAULT_COMPOUNDS,
    comparison_path: Path = DEFAULT_COMPARISON,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    total = int(comparison["saol_compared_records"])
    direct = int(comparison["saol_matched_records"])

    baseline_rows = [*read_jsonl(saol_only_path), *read_jsonl(ambiguous_path)]
    baseline = selector_counts(baseline_rows)
    baseline_records = sum(baseline.values())
    expected_baseline = total - direct
    if baseline_records != expected_baseline:
        raise RuntimeError(
            "Baslinjen stämmer inte: "
            f"{baseline_records} poster i saol14-only + ambiguous, "
            f"men jämförelserapporten kräver {expected_baseline}."
        )

    solved = solved_compound_counts(read_jsonl(compounds_path))
    unresolved, solved_in_baseline = subtract_counts(baseline, solved)
    expected_output = total - direct - solved_in_baseline
    unresolved_records = sum(unresolved.values())
    if unresolved_records != expected_output:
        raise RuntimeError(
            "Subtraktionskontrollen misslyckades: "
            f"{total} != {direct} + {solved_in_baseline} + {unresolved_records}. "
            "Ingen fil skrevs."
        )

    rows = filter_by_counts(read_jsonl(saol_path), unresolved)
    if len(rows) != expected_output:
        raise RuntimeError(
            "Exportkontrollen misslyckades: "
            f"{total} != {direct} + {solved_in_baseline} + {len(rows)}. "
            "Ingen fil skrevs."
        )

    write_jsonl(output_path, rows)
    return {
        "total": total,
        "direct": direct,
        "baseline_unresolved": baseline_records,
        "solved_compounds": solved_in_baseline,
        "records": len(rows),
        "output": str(output_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write original SAOL 14 JSONL records that are still unresolved"
    )
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saol-only", type=Path, default=DEFAULT_SAOL_ONLY)
    parser.add_argument("--ambiguous", type=Path, default=DEFAULT_AMBIGUOUS)
    parser.add_argument("--compounds", type=Path, default=DEFAULT_COMPOUNDS)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = export_unresolved(
        args.saol,
        args.saol_only,
        args.ambiguous,
        args.compounds,
        args.comparison,
        args.output,
    )
    print(f"SAOL-poster som jämförs:        {summary['total']}")
    print(f"Direkt lösta:                   {summary['direct']}")
    print(f"Säkra sammansättningar:         {summary['solved_compounds']}")
    print(f"Olösta SAOL-poster:             {summary['records']}")
    print(
        f"Kontroll: {summary['total']} = {summary['direct']} + "
        f"{summary['solved_compounds']} + {summary['records']} (OK)"
    )
    print(f"JSONL: {summary['output']}")


if __name__ == "__main__":
    main()
