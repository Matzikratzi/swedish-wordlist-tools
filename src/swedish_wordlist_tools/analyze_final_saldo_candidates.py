from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl


DEFAULT_INPUT = Path("reports/saol14-gamewords-saldo-review-candidates.jsonl")
DEFAULT_OUTPUT = Path("reports/saol14-gamewords-saldo-review-analysis.txt")


def _values(row: dict[str, Any], key: str) -> set[str]:
    return {
        str(item.get(key) or "<tom>")
        for item in row.get("matching_saldo_analyses", [])
    }


def _notations(row: dict[str, Any]) -> set[str]:
    return {
        str(item.get("notation") or "<tom>")
        for item in row.get("matching_saol_articles", [])
    }


def analyze(
    rows: Iterable[dict[str, Any]], examples_per_group: int = 25
) -> dict[str, Any]:
    materialized = list(rows)
    categories: Counter[str] = Counter()
    category_upos: Counter[tuple[str, str]] = Counter()
    category_msd: Counter[tuple[str, str]] = Counter()
    category_notation: Counter[tuple[str, str]] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    examples_by_upos: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in materialized:
        category = str(row.get("primary_category") or "<tom>")
        categories[category] += 1
        for upos in _values(row, "upos"):
            category_upos[(category, upos)] += 1
        for msd in _values(row, "msd"):
            category_msd[(category, msd)] += 1
        for notation in _notations(row):
            category_notation[(category, notation)] += 1
        if len(examples[category]) < examples_per_group:
            examples[category].append(row)
        for upos in _values(row, "upos"):
            key = (category, upos)
            if len(examples_by_upos[key]) < examples_per_group:
                examples_by_upos[key].append(row)

    return {
        "candidate_count": len(materialized),
        "categories": categories,
        "category_upos": category_upos,
        "category_msd": category_msd,
        "category_notation": category_notation,
        "examples": dict(examples),
        "examples_by_upos": dict(examples_by_upos),
    }


def _section_counter(
    title: str,
    counter: Counter[tuple[str, str]],
    category: str,
    limit: int,
) -> list[str]:
    values = Counter({
        value: count
        for (group, value), count in counter.items()
        if group == category
    })
    return [title, *(f"{count:8}  {value}" for value, count in values.most_common(limit))]


def _example_lines(row: dict[str, Any]) -> list[str]:
    lines = [f"  {str(row.get('form') or '')!r}"]
    for article in row.get("matching_saol_articles", [])[:3]:
        upos = ",".join(article.get("upos", []))
        lines.append(
            f"    SAOL {upos} ordkl={article.get('ordkl')!r} notation={article.get('notation')!r}"
        )
    for analysis in row.get("matching_saldo_analyses", [])[:3]:
        lemmas = ",".join(analysis.get("lemmas", []))
        lines.append(
            f"    SALDO {analysis.get('upos') or '<tom>'} msd={analysis.get('msd')!r} lemma={lemmas!r}"
        )
    return lines


def render(report: dict[str, Any], top: int = 30) -> str:
    lines = [
        "SAOL14: analys av SALDO-granskningskandidater",
        "",
        f"Kandidater: {report['candidate_count']}",
        "",
        "Efter primärkategori:",
    ]
    lines.extend(
        f"{count:8}  {category}"
        for category, count in report["categories"].most_common()
    )

    for category, _count in report["categories"].most_common():
        lines.extend(["", "=" * 78, category, ""])
        lines.extend(_section_counter("Efter UPOS:", report["category_upos"], category, top))
        lines.append("")
        lines.extend(_section_counter("Vanligaste SALDO-MSD:", report["category_msd"], category, top))
        lines.append("")
        lines.extend(_section_counter("Vanligaste SAOL-notationer:", report["category_notation"], category, top))
        upos_values = Counter({
            upos: count
            for (group, upos), count in report["category_upos"].items()
            if group == category
        })
        for upos, _upos_count in upos_values.most_common():
            lines.extend(["", f"Exempel {upos}:"])
            for row in report["examples_by_upos"].get((category, upos), []):
                lines.extend(_example_lines(row))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Group final SALDO review candidates by category, UPOS, MSD, and SAOL notation."
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--examples", type=int, default=25)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.input), examples_per_group=args.examples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(report, top=args.top), encoding="utf-8")
    print(f"Kandidater: {report['candidate_count']}")
    print(f"Rapport: {args.output}")


if __name__ == "__main__":
    main()
