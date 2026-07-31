from __future__ import annotations

import argparse
import json
import unicodedata
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

Selector = tuple[str, str]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _selector(row: dict[str, Any]) -> Selector | None:
    record_id = str(row.get("record_id") or row.get("id") or row.get("subnr") or "")
    if record_id:
        return "id", record_id

    lemma = _normalise(str(row.get("lemma") or row.get("normaliserat_ord") or ""))
    if lemma:
        homonym = str(row.get("homonym_number") or row.get("homonr") or "")
        upos = str(row.get("upos") or "").upper()
        return "fallback", "\x1f".join((lemma, homonym, upos))
    return None


def selectors(rows: Iterable[dict[str, Any]]) -> set[Selector]:
    result: set[Selector] = set()
    for row in rows:
        selector = _selector(row)
        if selector is not None:
            result.add(selector)
    return result


def solved_compound_selectors(rows: Iterable[dict[str, Any]]) -> set[Selector]:
    return selectors(
        row
        for row in rows
        if str(row.get("head_match_reason", "")) == SOLVED_COMPOUND_REASON
    )


def filter_unresolved(
    saol_rows: Iterable[dict[str, Any]],
    baseline_unresolved: set[Selector],
    solved_compounds: set[Selector],
) -> list[dict[str, Any]]:
    wanted = baseline_unresolved - solved_compounds
    result: list[dict[str, Any]] = []
    for row in saol_rows:
        selector = _selector(row)
        if selector in wanted:
            result.append(row)
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

    baseline_unresolved = selectors(
        [*read_jsonl(saol_only_path), *read_jsonl(ambiguous_path)]
    )
    solved_compounds = solved_compound_selectors(read_jsonl(compounds_path))

    expected_baseline = total - direct
    if len(baseline_unresolved) != expected_baseline:
        raise RuntimeError(
            "Baslinjen stämmer inte: "
            f"{len(baseline_unresolved)} unika poster i saol14-only + ambiguous, "
            f"men jämförelserapporten kräver {expected_baseline}."
        )

    solved_compounds_in_baseline = solved_compounds & baseline_unresolved
    rows = filter_unresolved(
        read_jsonl(saol_path), baseline_unresolved, solved_compounds_in_baseline
    )
    expected_output = total - direct - len(solved_compounds_in_baseline)

    if len(rows) != expected_output:
        raise RuntimeError(
            "Exportkontrollen misslyckades: "
            f"{total} != {direct} + {len(solved_compounds_in_baseline)} + {len(rows)}. "
            "Ingen fil skrevs."
        )

    write_jsonl(output_path, rows)
    return {
        "total": total,
        "direct": direct,
        "baseline_unresolved": len(baseline_unresolved),
        "solved_compounds": len(solved_compounds_in_baseline),
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
    print(f"Kontroll: {summary['total']} = {summary['direct']} + {summary['solved_compounds']} + {summary['records']} (OK)")
    print(f"JSONL: {summary['output']}")


if __name__ == "__main__":
    main()
