from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_JSON = Path("reports/saol14-saldo-missing-plural-analysis.json")
DEFAULT_TEXT = Path("reports/saol14-saldo-missing-plural-analysis.txt")
TARGET = "saldo_missing_plural"


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


def analyze_rows(rows: Iterable[dict[str, Any]], *, examples: int = 10) -> dict[str, Any]:
    selected = [row for row in rows if row.get("mismatch_classification") == TARGET]
    notation_counts = Counter(str(row.get("notation", "")) for row in selected)
    upos_counts = Counter(str(row.get("upos", "")) for row in selected)
    coverage_counts = Counter(str(row.get("coverage_status", "")) for row in selected)

    grouped: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in selected:
        lemma = str(row.get("lemma", ""))
        key = (
            str(row.get("notation", "")),
            _relative_forms(lemma, row.get("extra_from_saol", ())),
            _relative_forms(lemma, row.get("missing_from_saol", ())),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for (notation, extra, missing), members in grouped.items():
        members.sort(
            key=lambda row: (
                str(row.get("lemma", "")).casefold(),
                str(row.get("homonym_number", "")),
            )
        )
        groups.append(
            {
                "notation": notation,
                "count": len(members),
                "extra_pattern": list(extra),
                "missing_pattern": list(missing),
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
        )
    )

    return {
        "classification": TARGET,
        "records": len(selected),
        "notation_counts": dict(
            sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "upos_counts": dict(sorted(upos_counts.items(), key=lambda item: (-item[1], item[0]))),
        "coverage_status_counts": dict(
            sorted(coverage_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "groups": groups,
    }


def render_text(summary: dict[str, Any], *, max_groups: int = 80) -> str:
    lines = [
        "SAOL14 audit: saldo_missing_plural",
        "",
        f"Poster: {summary['records']}",
        f"Strukturgrupper: {len(summary['groups'])}",
        "",
        "Ordklass:",
    ]
    for name, count in summary["upos_counts"].items():
        lines.append(f"{count:5}  {name or '(tomt)'}")

    lines.extend(["", "Varianttäckning:"])
    for name, count in summary["coverage_status_counts"].items():
        lines.append(f"{count:5}  {name or '(tomt)'}")

    lines.extend(["", "Största notationer:"])
    for notation, count in list(summary["notation_counts"].items())[:40]:
        lines.append(f"{count:5}  {notation or '(tomt)'}")

    lines.extend(["", "Största exakta strukturgrupper:"])
    for index, group in enumerate(summary["groups"][:max_groups], start=1):
        extra = ", ".join(group["extra_pattern"]) or "–"
        missing = ", ".join(group["missing_pattern"]) or "–"
        example_text = ", ".join(
            item["lemma"]
            + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        lines.extend(
            [
                "",
                f"{index}. {group['count']} | {group['notation'] or '(tomt)'}",
                f"   Extra från SAOL: {extra}",
                f"   Saknas från SAOL: {missing}",
                f"   Exempel: {example_text}",
            ]
        )
    return "\n".join(lines) + "\n"


def analyze_file(
    input_path: Path = DEFAULT_INPUT,
    *,
    json_path: Path = DEFAULT_JSON,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    summary = analyze_rows(read_jsonl(input_path))
    summary.update({"input": str(input_path), "json": str(json_path), "text": str(text_path)})
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analysera exakta strukturmönster bland saldo_missing_plural-poster"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = analyze_file(args.input, json_path=args.json, text_path=args.text)
    print(f"Poster: {summary['records']}")
    print(f"Strukturgrupper: {len(summary['groups'])}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
