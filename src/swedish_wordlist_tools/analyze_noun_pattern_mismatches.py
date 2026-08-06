from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-pattern-mismatches.txt")
DEFAULT_JSON = Path("reports/saol14-noun-pattern-mismatches.json")
DEFAULT_NOTATION = "+en +er"


def _relative_form(lemma: str, form: str) -> str:
    lemma_folded = lemma.casefold()
    form_folded = form.casefold()
    if lemma_folded and form_folded.startswith(lemma_folded):
        return "+" + form_folded[len(lemma_folded) :]
    return "=" + form_folded


def _relative_forms(lemma: str, forms: Iterable[object]) -> tuple[str, ...]:
    return tuple(sorted(_relative_form(lemma, str(form)) for form in forms))


def analyse_rows(
    rows: Iterable[dict[str, Any]],
    *,
    notation: str = DEFAULT_NOTATION,
    examples: int = 12,
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if str(row.get("upos", "")).upper() == "NOUN"
        and str(row.get("status", "")) == "form_set_mismatch"
        and str(row.get("notation", "")) == notation
    ]

    grouped: dict[tuple[tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        lemma = str(row.get("lemma", ""))
        key = (
            _relative_forms(lemma, row.get("extra_from_saol", ())),
            _relative_forms(lemma, row.get("missing_from_saol", ())),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for (extra, missing), members in grouped.items():
        members.sort(
            key=lambda row: (
                str(row.get("lemma", "")).casefold(),
                str(row.get("homonym_number", "")),
            )
        )
        groups.append(
            {
                "count": len(members),
                "extra_pattern": list(extra),
                "missing_pattern": list(missing),
                "examples": [
                    {
                        "lemma": str(row.get("lemma", "")),
                        "homonym_number": str(row.get("homonym_number", "")),
                        "generated_forms": list(row.get("generated_forms", ())),
                        "saldo_forms": list(row.get("saldo_forms", ())),
                        "extra_from_saol": list(row.get("extra_from_saol", ())),
                        "missing_from_saol": list(row.get("missing_from_saol", ())),
                    }
                    for row in members[:examples]
                ],
            }
        )

    groups.sort(
        key=lambda group: (
            -int(group["count"]),
            tuple(group["extra_pattern"]),
            tuple(group["missing_pattern"]),
        )
    )
    direction_counts = Counter(
        "both"
        if group["extra_pattern"] and group["missing_pattern"]
        else "extra_only"
        if group["extra_pattern"]
        else "missing_only"
        for group in groups
        for _ in range(int(group["count"]))
    )
    return {
        "notation": notation,
        "records": len(selected),
        "groups": groups,
        "direction_counts": dict(sorted(direction_counts.items())),
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


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Notation: {report['notation']}",
        f"Mismatchposter: {report['records']}",
        "",
        "Riktning:",
    ]
    if not report["direction_counts"]:
        lines.append("  (inga)")
    for direction, count in report["direction_counts"].items():
        lines.append(f"{count:5}  {direction}")

    lines.extend(["", "Grupper efter relativ formskillnad:"])
    if not report["groups"]:
        lines.append("  (inga)")
    for index, group in enumerate(report["groups"], start=1):
        extra = ", ".join(group["extra_pattern"]) or "–"
        missing = ", ".join(group["missing_pattern"]) or "–"
        examples = ", ".join(
            item["lemma"]
            + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        lines.extend(
            [
                "",
                f"{index}. {group['count']} poster",
                f"   Extra från SAOL-generatorn: {extra}",
                f"   Saknas från SAOL-generatorn: {missing}",
                f"   Exempel: {examples}",
            ]
        )
        for item in group["examples"][:3]:
            lines.append(
                "   "
                + item["lemma"]
                + ": genererat="
                + repr(item["generated_forms"])
                + " SALDO="
                + repr(item["saldo_forms"])
            )
    return "\n".join(lines) + "\n"


def analyse_file(
    input_path: Path = DEFAULT_INPUT,
    *,
    notation: str = DEFAULT_NOTATION,
    text_path: Path = DEFAULT_TEXT,
    json_path: Path = DEFAULT_JSON,
    examples: int = 12,
) -> dict[str, Any]:
    report = analyse_rows(read_jsonl(input_path), notation=notation, examples=examples)
    report.update(
        {
            "input": str(input_path),
            "text": str(text_path),
            "json": str(json_path),
        }
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(report), encoding="utf-8")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gruppera kanoniska substantivmismatchar för en exakt SAOL-notation"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--notation", default=DEFAULT_NOTATION)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--examples", type=int, default=12)
    args = parser.parse_args()
    if args.examples < 1:
        raise SystemExit("--examples måste vara minst 1")
    report = analyse_file(
        args.input,
        notation=args.notation,
        text_path=args.text,
        json_path=args.json,
        examples=args.examples,
    )
    print(f"Notation: {report['notation']}")
    print(f"Mismatchposter: {report['records']}")
    print(f"Grupper: {len(report['groups'])}")
    print(f"Text: {report['text']}")
    print(f"JSON: {report['json']}")


if __name__ == "__main__":
    main()
