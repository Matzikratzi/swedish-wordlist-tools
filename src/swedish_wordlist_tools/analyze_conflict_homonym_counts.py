from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, read_saldo_forms

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-conflict-homonym-counts.txt")
DEFAULT_JSON = Path("reports/saol14-conflict-homonym-counts.json")


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


def _saol_homonym_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        lemma = _key(row.get("normaliserat_ord"))
        upos = str(row.get("upos") or "").upper()
        if not lemma or not upos:
            continue
        hom = str(row.get("homonr") or "")
        # homonr=0 is a materialized alias/variant row in this source and must
        # not be counted as an additional dictionary homonym.
        if hom in {"", "0"}:
            continue
        index[(lemma, upos)].add(hom)
    return index


def _saldo_analysis_index(path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    saldo = read_saldo_forms(path)
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            upos = str(analysis.get("upos") or "").upper()
            forms = tuple(sorted(str(v).casefold() for v in analysis.get("forms", ())))
            aid = str(analysis.get("id") or "")
            for lemma in analysis.get("lemmas", ()):
                lemma_key = _key(lemma)
                marker = (lemma_key, upos, aid, forms)
                if lemma_key and marker not in seen:
                    seen.add(marker)
                    index[(lemma_key, upos)].append(analysis)
    return index


def analyze(validation_rows: list[dict[str, Any]], saol_rows: list[dict[str, Any]], saldo_path: Path) -> dict[str, Any]:
    saol_index = _saol_homonym_index(saol_rows)
    saldo_index = _saldo_analysis_index(saldo_path)

    selected = [
        row for row in validation_rows
        if str(row.get("upos") or "").upper() == "NOUN"
        and str(row.get("status") or "") == "form_set_mismatch"
    ]

    counts = Counter()
    rows: list[dict[str, Any]] = []
    for row in selected:
        lemma = str(row.get("lemma") or "")
        key = (_key(lemma), "NOUN")
        saol_homs = sorted(saol_index.get(key, set()))
        saldo_analyses = saldo_index.get(key, [])
        saldo_ids = sorted({str(a.get("id") or "") for a in saldo_analyses})
        saol_count = len(saol_homs)
        saldo_count = len(saldo_analyses)
        if saol_count == saldo_count and saol_count > 1:
            bucket = "same_multiple_count"
        elif saol_count > 1 and saldo_count > 1:
            bucket = "different_multiple_count"
        elif saol_count > 1 and saldo_count <= 1:
            bucket = "saol_multiple_saldo_single"
        elif saol_count <= 1 and saldo_count > 1:
            bucket = "saol_single_saldo_multiple"
        else:
            bucket = "both_single_or_missing"
        counts[bucket] += 1
        rows.append({
            "lemma": lemma,
            "saol_homonym_number": str(row.get("homonym_number") or ""),
            "saol_homonym_count": saol_count,
            "saol_homonym_numbers": saol_homs,
            "saldo_analysis_count": saldo_count,
            "saldo_analysis_ids": saldo_ids,
            "validation_saldo_ids": list(row.get("saldo_ids", ())),
            "match_method": str(row.get("match_method") or ""),
            "notation": str(row.get("notation") or ""),
            "bucket": bucket,
        })

    rows.sort(key=lambda r: (r["bucket"], -r["saol_homonym_count"], -r["saldo_analysis_count"], r["lemma"].casefold()))
    return {"records": len(rows), "counts": dict(counts.most_common()), "rows": rows}


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14/SALDO: homonymantal bland NOUN form_set_mismatch",
        "",
        f"Poster: {summary['records']}",
        "",
        "Fördelning:",
    ]
    for name, count in summary["counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Fall där homonymer kan vara relevanta:"])
    interesting = [r for r in summary["rows"] if r["bucket"] != "both_single_or_missing"]
    for row in interesting[:200]:
        lines.append(
            f"  {row['lemma']} | SAOL {row['saol_homonym_count']} {row['saol_homonym_numbers']} "
            f"| SALDO {row['saldo_analysis_count']} ids={row['saldo_analysis_ids']} "
            f"| denna SAOL-homonym={row['saol_homonym_number']} | match={row['match_method']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.validation), read_jsonl(args.saol), args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for name, count in summary["counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
