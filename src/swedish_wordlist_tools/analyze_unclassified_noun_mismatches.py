from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_JSON = Path("reports/saol14-unclassified-noun-mismatches.json")
DEFAULT_TEXT = Path("reports/saol14-unclassified-noun-mismatches.txt")


def _relative_form(lemma: str, form: object) -> str:
    lemma_folded = lemma.casefold()
    form_folded = str(form).casefold()
    if lemma_folded and form_folded.startswith(lemma_folded):
        return "+" + form_folded[len(lemma_folded) :]
    return "=" + form_folded


def _relative_forms(lemma: str, values: Iterable[object]) -> tuple[str, ...]:
    return tuple(sorted(_relative_form(lemma, value) for value in values))


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


def analyze_rows(rows: Iterable[dict[str, Any]], *, examples: int = 12) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if str(row.get("upos", "")).upper() == "NOUN"
        and str(row.get("mismatch_classification", "")) == "unclassified"
    ]

    notation_counts: Counter[str] = Counter()
    match_method_counts: Counter[str] = Counter()
    coverage_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    grouped: dict[
        tuple[str, tuple[str, ...], tuple[str, ...], str, str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in selected:
        lemma = str(row.get("lemma", ""))
        notation = str(row.get("notation", "")).strip()
        match_method = str(row.get("match_method", ""))
        coverage = str(row.get("coverage_status", ""))
        reason = str(row.get("paradigm_reason", ""))
        notation_counts[notation] += 1
        match_method_counts[match_method] += 1
        coverage_counts[coverage] += 1
        reason_counts[reason] += 1
        grouped[
            (
                notation,
                _relative_forms(lemma, row.get("extra_from_saol", ())),
                _relative_forms(lemma, row.get("missing_from_saol", ())),
                match_method,
                coverage,
                reason,
            )
        ].append(row)

    groups: list[dict[str, Any]] = []
    for (notation, extra, missing, match_method, coverage, reason), members in grouped.items():
        members.sort(
            key=lambda row: (
                str(row.get("lemma", "")).casefold(),
                str(row.get("homonym_number", "")),
            )
        )
        groups.append(
            {
                "count": len(members),
                "notation": notation,
                "extra_pattern": list(extra),
                "missing_pattern": list(missing),
                "match_method": match_method,
                "coverage_status": coverage,
                "paradigm_reason": reason,
                "examples": [
                    {
                        "lemma": str(row.get("lemma", "")),
                        "homonym_number": str(row.get("homonym_number", "")),
                        "record_id": str(row.get("record_id", "")),
                    }
                    for row in members[:examples]
                ],
            }
        )

    groups.sort(
        key=lambda group: (
            -int(group["count"]),
            str(group["notation"]),
            tuple(group["extra_pattern"]),
            tuple(group["missing_pattern"]),
            str(group["match_method"]),
        )
    )

    return {
        "records": len(selected),
        "structure_groups": len(groups),
        "notation_counts": dict(
            sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "match_method_counts": dict(
            sorted(match_method_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "paradigm_reason_counts": dict(
            sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "groups": groups,
    }


def render_text(summary: dict[str, Any], *, max_groups: int = 60) -> str:
    lines = [
        "SAOL14 audit: oklassificerade NOUN-paradigmmismatchar",
        "",
        f"Poster: {summary['records']}",
        f"Strukturgrupper: {summary['structure_groups']}",
        "",
        "Största notationer:",
    ]
    for notation, count in list(summary["notation_counts"].items())[:40]:
        lines.append(f"{count:5d}  {notation or '(tomt)'}")

    lines.extend(["", "Matchningsmetoder:"])
    for name, count in summary["match_method_counts"].items():
        lines.append(f"{count:5d}  {name or '(tomt)'}")

    lines.extend(["", "Varianttäckning:"])
    for name, count in summary["coverage_status_counts"].items():
        lines.append(f"{count:5d}  {name or '(tomt)'}")

    lines.extend(["", "Paradigmorsaker:"])
    for name, count in summary["paradigm_reason_counts"].items():
        lines.append(f"{count:5d}  {name or '(tomt)'}")

    lines.extend(["", "Största exakta strukturgrupper:"])
    for index, group in enumerate(summary["groups"][:max_groups], start=1):
        extra = ", ".join(group["extra_pattern"]) or "–"
        missing = ", ".join(group["missing_pattern"]) or "–"
        examples = ", ".join(
            f"{item['lemma']} ({item['homonym_number']})"
            if item["homonym_number"]
            else item["lemma"]
            for item in group["examples"]
        )
        lines.extend(
            [
                "",
                f"{index}. {group['count']} | {group['notation'] or '(tomt)'}",
                f"   match={group['match_method'] or '(tomt)'} coverage={group['coverage_status'] or '(tomt)'} reason={group['paradigm_reason'] or '(tomt)'}",
                f"   Extra från SAOL: {extra}",
                f"   Saknas från SAOL: {missing}",
                f"   Exempel: {examples}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gruppera alla oklassificerade NOUN-paradigmmismatchar efter exakt struktur"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    summary = analyze_rows(read_jsonl(args.input))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.text.write_text(render_text(summary), encoding="utf-8")

    print(f"Oklassificerade NOUN: {summary['records']}")
    print(f"Strukturgrupper: {summary['structure_groups']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
