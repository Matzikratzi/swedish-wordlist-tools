from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analyze_homonym_paradigm_matching import _formset, _homonym, _key, _lemma, _rows_by_lemma
from .jsonl import read_jsonl
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, read_saldo_forms

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-unequal-homonym-paradigm-coverage.txt")
DEFAULT_JSON = Path("reports/saol14-unequal-homonym-paradigm-coverage.json")


def _saldo_by_lemma(path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped = read_saldo_forms(path)
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for analyses in grouped.values():
        for analysis in analyses:
            upos = str(analysis.get("upos") or "").upper()
            forms = tuple(sorted(_formset(analysis.get("forms"))))
            aid = str(analysis.get("id") or "")
            for lemma_value in analysis.get("lemmas", ()):
                lemma = _key(lemma_value)
                marker = (lemma, upos, aid, forms)
                if lemma and marker not in seen:
                    seen.add(marker)
                    result[(lemma, upos)].append(analysis)
    return result


def compare_one(saol: dict[str, Any], saldo: dict[str, Any]) -> dict[str, Any]:
    sf = _formset(saol.get("generated_forms"))
    df = _formset(saldo.get("forms"))
    return {
        "saol_homonym": _homonym(saol),
        "saldo_id": str(saldo.get("id") or ""),
        "exact": sf == df,
        "saol_subset": sf <= df,
        "overlap": len(sf & df),
        "saol_only": sorted(sf - df),
        "saldo_only": sorted(df - sf),
    }


def analyze(validation_rows: list[dict[str, Any]], saol_rows: list[dict[str, Any]], saldo_path: Path) -> dict[str, Any]:
    generated = _rows_by_lemma(validation_rows)
    raw = _rows_by_lemma(saol_rows)
    saldo = _saldo_by_lemma(saldo_path)
    conflict_keys = {
        (_lemma(row), "NOUN")
        for row in validation_rows
        if str(row.get("upos") or "").upper() == "NOUN"
        and str(row.get("status") or "") == "form_set_mismatch"
        and _lemma(row)
    }

    rows: list[dict[str, Any]] = []
    pattern_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for key in sorted(conflict_keys):
        sr = generated.get(key, ())
        rr = raw.get(key, ())
        dr = saldo.get(key, ())
        if len(rr) <= 1 or len(sr) != len(rr) or len(dr) == len(rr):
            continue

        comparisons = [compare_one(s, d) for s in sr for d in dr]
        exact_homs = sorted({c["saol_homonym"] for c in comparisons if c["exact"]})
        subset_homs = sorted({c["saol_homonym"] for c in comparisons if c["saol_subset"]})

        if exact_homs:
            status = "at_least_one_saol_homonym_exactly_verified"
        elif subset_homs:
            status = "at_least_one_saol_homonym_subset_verified"
        else:
            status = "no_saol_homonym_verified"
        status_counts[status] += 1

        pattern = f"SAOL={len(rr)} SALDO={len(dr)}"
        pattern_counts[pattern] += 1

        best = sorted(
            comparisons,
            key=lambda c: (c["exact"], c["saol_subset"], c["overlap"], -len(c["saol_only"]), -len(c["saldo_only"])),
            reverse=True,
        )[: min(6, len(comparisons))]
        rows.append({
            "lemma": key[0],
            "saol_count": len(rr),
            "saldo_count": len(dr),
            "status": status,
            "exact_saol_homonyms": exact_homs,
            "subset_saol_homonyms": subset_homs,
            "best_matches": best,
        })

    return {
        "lemmas": len(rows),
        "count_patterns": dict(pattern_counts.most_common()),
        "status_counts": dict(status_counts.most_common()),
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14/SALDO: homonymtäckning när antalet analyser skiljer sig",
        "",
        f"Lemman: {summary['lemmas']}",
        "",
        "Antalsmönster:",
    ]
    for pattern, count in summary["count_patterns"].items():
        lines.append(f"{count:5}  {pattern}")
    lines.extend(["", "Verifieringsstatus:"])
    for status, count in summary["status_counts"].items():
        lines.append(f"{count:5}  {status}")
    lines.extend(["", "Detaljer:"])
    for row in summary["rows"]:
        lines.append(
            f"\n{row['lemma']} | SAOL={row['saol_count']} SALDO={row['saldo_count']} | {row['status']} "
            f"| exact SAOL-homonymer={row['exact_saol_homonyms'] or '–'} "
            f"| subset SAOL-homonymer={row['subset_saol_homonyms'] or '–'}"
        )
        for match in row["best_matches"]:
            lines.append(
                f"  SAOL {match['saol_homonym']} -> SALDO {match['saldo_id'] or '(id saknas)'} "
                f"exact={match['exact']} subset={match['saol_subset']} overlap={match['overlap']} "
                f"SAOL-only={match['saol_only'] or '–'} SALDO-only={match['saldo_only'] or '–'}"
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

    summary = analyze(list(read_jsonl(args.validation)), list(read_jsonl(args.saol)), args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Lemman: {summary['lemmas']}")
    for pattern, count in summary["count_patterns"].items():
        print(f"{pattern}: {count}")
    for status, count in summary["status_counts"].items():
        print(f"{status}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
