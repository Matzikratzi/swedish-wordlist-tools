from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-next-noun-mismatch-patterns.json")
DEFAULT_TEXT = Path("reports/saol14-next-noun-mismatch-patterns.txt")


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def _forms(lemma: str, suffixes: Iterable[str]) -> set[str]:
    return {lemma.casefold() + suffix for suffix in suffixes}


def candidate_kind(row: dict[str, Any]) -> str | None:
    if str(row.get("mismatch_classification") or "") != "unclassified":
        return None
    if str(row.get("upos") or "").upper() != "NOUN":
        return None

    lemma = str(row.get("lemma") or "").casefold()
    notation = str(row.get("notation") or "").strip()
    if not lemma:
        return None
    extra = _casefolded(row.get("extra_from_saol", ()))
    missing = _casefolded(row.get("missing_from_saol", ()))

    # SAOL explicitly has neuter definite singular only; SALDO instead has
    # common-gender definite singular plus one complete regular plural.
    if notation == "+et" and extra == _forms(lemma, ("et", "ets")):
        for name, suffixes in (
            ("et_vs_en_er", ("en", "ens", "er", "ers", "erna", "ernas")),
            ("et_vs_en_ar", ("en", "ens", "ar", "ars", "arna", "arnas")),
        ):
            if missing == _forms(lemma, suffixes):
                return name

    # SAOL notation explicitly marks zero plural.  These rows are audited
    # separately because an apparent singular/plural reinterpretation in SALDO
    # deserves inspection before becoming a general classification rule.
    if (
        notation == "pl. +"
        and extra == _forms(lemma, ("na", "nas"))
        and missing == _forms(lemma, ("en", "ens"))
    ):
        return "zero_plural_vs_definite_singular"

    return None


def analyze_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        kind = candidate_kind(row)
        if not kind:
            continue
        counts[kind] += 1
        bucket = examples.setdefault(kind, [])
        if len(bucket) < 20:
            bucket.append(
                {
                    "lemma": str(row.get("lemma") or ""),
                    "homonym_number": str(row.get("homonym_number") or ""),
                    "notation": str(row.get("notation") or ""),
                }
            )
    return {
        "candidate_counts": dict(sorted(counts.items())),
        "candidate_total": sum(counts.values()),
        "examples": examples,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def render(summary: dict[str, Any]) -> str:
    lines = [
        "Nästa mekaniska NOUN-kandidater",
        "",
        f"Totalt: {summary['candidate_total']}",
    ]
    for kind, count in summary["candidate_counts"].items():
        lines.extend(["", f"{kind}: {count}"])
        for example in summary["examples"].get(kind, []):
            hom = example["homonym_number"]
            lines.append(f"  {example['lemma']}" + (f" ({hom})" if hom else ""))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit next exact noun mismatch patterns")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    summary = analyze_rows(read_jsonl(args.input))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.write_text(render(summary), encoding="utf-8")
    print(f"Kandidater totalt: {summary['candidate_total']}")
    for kind, count in summary["candidate_counts"].items():
        print(f"{kind}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.summary}")


if __name__ == "__main__":
    main()
