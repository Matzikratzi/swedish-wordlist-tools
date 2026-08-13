from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSON = Path("reports/saol14-paradigm-differences-summary.json")
DEFAULT_TEXT = Path("reports/saol14-paradigm-differences.txt")
TARGET_STATUS = "saol_paradigm_differs_from_saldo"


def _normalised_suffixes(lemma: str, forms: Iterable[str]) -> tuple[str, ...]:
    """Describe forms as lemma-relative suffixes when possible."""
    suffixes: list[str] = []
    lemma_folded = lemma.casefold()
    for form in forms:
        form_folded = str(form).casefold()
        if form_folded.startswith(lemma_folded):
            suffixes.append("+" + form_folded[len(lemma_folded) :])
        else:
            suffixes.append("=" + form_folded)
    return tuple(sorted(suffixes))


def _group_key(row: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    lemma = str(row.get("lemma", ""))
    return (
        str(row.get("notation", "")),
        _normalised_suffixes(lemma, row.get("extra_from_saol", [])),
        _normalised_suffixes(lemma, row.get("missing_from_saol", [])),
    )


def analyse_rows(rows: Iterable[dict[str, Any]], examples: int = 10) -> dict[str, Any]:
    selected = [row for row in rows if row.get("status") == TARGET_STATUS]
    by_notation = Counter(str(row.get("notation", "")) for row in selected)
    grouped: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for row in selected:
        grouped[_group_key(row)].append(row)

    groups: list[dict[str, Any]] = []
    for (notation, extra_pattern, missing_pattern), members in grouped.items():
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
                "extra_pattern": list(extra_pattern),
                "missing_pattern": list(missing_pattern),
                "examples": [
                    {
                        "lemma": str(row.get("lemma", "")),
                        "homonym_number": str(row.get("homonym_number", "")),
                        "extra_from_saol": list(row.get("extra_from_saol", [])),
                        "missing_from_saol": list(row.get("missing_from_saol", [])),
                        "saldo_lemmas": list(row.get("saldo_lemmas", [])),
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
        "status": TARGET_STATUS,
        "records": len(selected),
        "notation_counts": dict(sorted(by_notation.items(), key=lambda item: (-item[1], item[0]))),
        "groups": groups,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {line_number} i {path}") from error
    return rows


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Poster: {summary['records']}",
        "",
        "Per SAOL-notation:",
    ]
    for notation, count in summary["notation_counts"].items():
        lines.append(f"{count:5}  {notation}")

    lines.extend(["", "Grupper efter formskillnad:"])
    for index, group in enumerate(summary["groups"], start=1):
        lines.extend(
            [
                "",
                f"{index}. {group['notation']} — {group['count']} poster",
                "   Extra från SAOL: " + (", ".join(group["extra_pattern"]) or "–"),
                "   Saknas från SAOL: " + (", ".join(group["missing_pattern"]) or "–"),
                "   Exempel: "
                + ", ".join(
                    example["lemma"]
                    + (f" ({example['homonym_number']})" if example["homonym_number"] else "")
                    for example in group["examples"]
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def analyse_file(
    input_path: Path = DEFAULT_INPUT,
    json_path: Path = DEFAULT_JSON,
    text_path: Path = DEFAULT_TEXT,
    examples: int = 10,
) -> dict[str, Any]:
    summary = analyse_rows(read_jsonl(input_path), examples=examples)
    summary["input"] = str(input_path)
    summary["json"] = str(json_path)
    summary["text"] = str(text_path)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gruppera SAOL–SALDO-paradigmskillnader efter notation och formmönster"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--examples", type=int, default=10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.examples < 1:
        raise SystemExit("--examples måste vara minst 1")
    summary = analyse_file(args.input, args.json, args.text, args.examples)
    print(f"Paradigmskillnader: {summary['records']}")
    for notation, count in summary["notation_counts"].items():
        print(f"{notation}: {count}")
    print(f"Grupper: {len(summary['groups'])}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
