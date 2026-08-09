from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .saldo_form_artifact import DEFAULT_SALDO_FORMS, read_saldo_forms

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-homonym-paradigm-matching.txt")
DEFAULT_JSON = Path("reports/saol14-homonym-paradigm-matching.json")


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


def _formset(values: object) -> set[str]:
    return {str(value).casefold() for value in (values or ()) if str(value)}


def _lemma(row: dict[str, Any]) -> str:
    return _key(row.get("lemma") or row.get("normaliserat_ord"))


def _homonym(row: dict[str, Any]) -> str:
    return str(row.get("homonym_number") or row.get("homonr") or "")


def _rows_by_lemma(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        lemma = _lemma(row)
        upos = str(row.get("upos") or "").upper()
        hom = _homonym(row)
        if not lemma or not upos or hom in {"", "0"}:
            continue
        marker = (lemma, upos, hom)
        if marker not in seen:
            seen.add(marker)
            result[(lemma, upos)].append(row)
    return result


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


def pair_score(saol: dict[str, Any], saldo: dict[str, Any]) -> tuple[int, int, int]:
    sf = _formset(saol.get("generated_forms"))
    df = _formset(saldo.get("forms"))
    return int(sf == df), len(sf & df), -len(sf ^ df)


def best_assignment(saol_rows: list[dict[str, Any]], saldo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(saol_rows) != len(saldo_rows) or len(saol_rows) < 2:
        raise ValueError("best_assignment requires equal multiple analysis counts")
    best = None
    tied = 0
    for perm in itertools.permutations(range(len(saldo_rows))):
        scores = [pair_score(saol_rows[i], saldo_rows[j]) for i, j in enumerate(perm)]
        total = tuple(sum(score[k] for score in scores) for k in range(3))
        if best is None or total > best[0]:
            best = (total, perm)
            tied = 1
        elif total == best[0]:
            tied += 1
    assert best is not None
    total, perm = best
    pairs = []
    for i, j in enumerate(perm):
        sf = _formset(saol_rows[i].get("generated_forms"))
        df = _formset(saldo_rows[j].get("forms"))
        pairs.append({
            "saol_homonym": _homonym(saol_rows[i]),
            "saldo_id": str(saldo_rows[j].get("id") or ""),
            "exact": sf == df,
            "overlap": len(sf & df),
            "saol_only": sorted(sf - df),
            "saldo_only": sorted(df - sf),
        })
    return {"score": list(total), "tie_count": tied, "pairs": pairs}


def analyze(validation_rows: list[dict[str, Any]], saol_rows: list[dict[str, Any]], saldo_path: Path) -> dict[str, Any]:
    generated = _rows_by_lemma(validation_rows)
    raw = _rows_by_lemma(saol_rows)
    saldo = _saldo_by_lemma(saldo_path)
    conflict_keys = {
        (_lemma(row), "NOUN") for row in validation_rows
        if str(row.get("upos") or "").upper() == "NOUN"
        and str(row.get("status") or "") == "form_set_mismatch" and _lemma(row)
    }
    rows = []
    counts = Counter()
    excluded = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for key in sorted(conflict_keys):
        raw_count = len(raw.get(key, ()))
        sr = generated.get(key, ())
        dr = saldo.get(key, ())
        if raw_count <= 1:
            reason = "saol_not_multiple"
        elif len(sr) != raw_count:
            reason = "validation_count_differs_from_saol"
        elif len(dr) != raw_count:
            reason = "saldo_count_differs_from_saol"
        else:
            reason = ""
        if reason:
            excluded[reason] += 1
            if len(examples[reason]) < 20:
                examples[reason].append(f"{key[0]} (SAOL={raw_count}, validation={len(sr)}, SALDO={len(dr)})")
            continue
        assignment = best_assignment(sr, dr)
        exact_pairs = sum(int(pair["exact"]) for pair in assignment["pairs"])
        if exact_pairs == len(sr):
            status = "all_pairs_exact"
        elif exact_pairs:
            status = "some_pairs_exact"
        elif assignment["tie_count"] == 1:
            status = "unique_best_no_exact_pairs"
        else:
            status = "ambiguous_best"
        counts[status] += 1
        rows.append({"lemma": key[0], "homonym_count": raw_count, "status": status, **assignment})
    return {"conflict_lemmas": len(conflict_keys), "lemmas": len(rows), "counts": dict(counts.most_common()), "excluded": dict(excluded.most_common()), "excluded_examples": dict(examples), "rows": rows}


def render(summary: dict[str, Any]) -> str:
    lines = ["SAOL14/SALDO: global paradigmmatchning av homonymer", "", f"Konfliktlemman: {summary['conflict_lemmas']}", f"Jämförbara homonymlemman: {summary['lemmas']}", "", "Exkluderade:"]
    for name, count in summary["excluded"].items():
        lines.append(f"{count:5}  {name}")
        for example in summary["excluded_examples"].get(name, ()):
            lines.append(f"       {example}")
    lines.extend(["", "Resultat:"])
    for name, count in summary["counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Matchningar:"])
    for row in summary["rows"]:
        lines.append(f"\n{row['lemma']} | homonymer={row['homonym_count']} | {row['status']} | bästa lösningar={row['tie_count']}")
        for pair in row["pairs"]:
            lines.append(f"  SAOL {pair['saol_homonym']} -> SALDO {pair['saldo_id'] or '(id saknas)'} | exact={pair['exact']} overlap={pair['overlap']} | SAOL-only={pair['saol_only'] or '–'} | SALDO-only={pair['saldo_only'] or '–'}")
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
    print(f"Konfliktlemman: {summary['conflict_lemmas']}")
    print(f"Jämförbara homonymlemman: {summary['lemmas']}")
    for name, count in summary["excluded"].items(): print(f"excluded {name}: {count}")
    for name, count in summary["counts"].items(): print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
