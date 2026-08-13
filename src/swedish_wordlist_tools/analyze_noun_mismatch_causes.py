from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSON = Path("reports/saol14-noun-mismatch-causes.json")
DEFAULT_TEXT = Path("reports/saol14-noun-mismatch-causes.txt")


def _folded(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values}


def _suffixes(lemma: str, forms: Iterable[str]) -> set[str]:
    folded_lemma = lemma.casefold()
    result: set[str] = set()
    for value in forms:
        form = str(value).casefold()
        if folded_lemma and form.startswith(folded_lemma):
            result.add("+" + form[len(folded_lemma) :])
        else:
            result.add("=" + form)
    return result


def _is_regular_plural_family(suffixes: set[str], ending: str) -> bool:
    return suffixes == {
        "+" + ending,
        "+" + ending + "s",
        "+" + ending + "na",
        "+" + ending + "nas",
    }


def classify_cause(row: dict[str, Any]) -> str:
    lemma = str(row.get("lemma", ""))
    notation = str(row.get("notation", ""))
    extra = _suffixes(lemma, row.get("extra_from_saol", []))
    missing = _suffixes(lemma, row.get("missing_from_saol", []))
    folded_notation = notation.casefold()

    if "som:" in folded_notation or "anv." in folded_notation or "används" in folded_notation:
        if any(value.startswith("=") for value in extra):
            return "lexicographic_comment_not_parsed"
        return "explicit_alternative_form_comment"

    if " el. " in folded_notation:
        if "pl." in folded_notation:
            return "alternative_gender_or_plural"
        return "alternative_gender"

    if "pl. +" in folded_notation and (
        _is_regular_plural_family(missing, "ar")
        or _is_regular_plural_family(missing, "er")
    ):
        return "zero_plural_vs_regular_plural"

    if (
        _is_regular_plural_family(extra, "ar")
        and _is_regular_plural_family(missing, "er")
    ) or (
        _is_regular_plural_family(extra, "er")
        and _is_regular_plural_family(missing, "ar")
    ):
        return "competing_regular_plural_endings"

    if extra in ({"+et", "+ets"}, {"+en", "+ens"}) and not missing:
        return "saldo_missing_definite_singular"

    if extra in ({"+et", "+ets"}, {"+en", "+ens"}) and missing:
        return "competing_gender_or_number_paradigm"

    if extra and not missing:
        return "saol_has_additional_forms"
    if missing and not extra:
        return "saldo_has_additional_forms"

    return "unknown_mixed_difference"


def analyse_rows(rows: Iterable[dict[str, Any]], examples: int = 12) -> dict[str, Any]:
    nouns = [
        row
        for row in rows
        if row.get("status") == "form_set_mismatch" and row.get("upos") == "NOUN"
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        grouped[classify_cause(row)].append(row)

    causes: list[dict[str, Any]] = []
    for cause, members in grouped.items():
        members.sort(key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("homonym_number", ""))))
        causes.append({
            "cause": cause,
            "count": len(members),
            "notation_counts": dict(Counter(str(row.get("notation", "")) for row in members).most_common()),
            "examples": [
                {
                    "lemma": str(row.get("lemma", "")),
                    "homonym_number": str(row.get("homonym_number", "")),
                    "notation": str(row.get("notation", "")),
                    "extra_from_saol": list(row.get("extra_from_saol", [])),
                    "missing_from_saol": list(row.get("missing_from_saol", [])),
                }
                for row in members[:examples]
            ],
        })
    causes.sort(key=lambda item: (-int(item["count"]), str(item["cause"])))
    return {
        "remaining_noun_mismatches": len(nouns),
        "cause_count": len(causes),
        "causes": causes,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Kvarvarande substantivmismatch: {summary['remaining_noun_mismatches']}",
        f"Föreslagna orsakskategorier: {summary['cause_count']}",
        "",
    ]
    for index, cause in enumerate(summary["causes"], start=1):
        notation_text = ", ".join(
            f"{notation} ({count})"
            for notation, count in list(cause["notation_counts"].items())[:10]
        )
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in cause["examples"]
        )
        lines.extend([
            f"{index}. {cause['cause']}: {cause['count']} poster",
            "   Notationer: " + (notation_text or "–"),
            "   Exempel: " + (examples or "–"),
            "",
        ])
    return "\n".join(lines)


def analyse_file(
    input_path: Path = DEFAULT_INPUT,
    json_path: Path = DEFAULT_JSON,
    text_path: Path = DEFAULT_TEXT,
    examples: int = 12,
) -> dict[str, Any]:
    summary = analyse_rows(read_jsonl(input_path), examples)
    summary.update({"input": str(input_path), "json": str(json_path), "text": str(text_path)})
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Klassificera sannolika orsaker till kvarvarande substantivmismatch")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--examples", type=int, default=12)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.examples < 1:
        raise SystemExit("--examples måste vara minst 1")
    summary = analyse_file(args.input, args.json, args.text, args.examples)
    print(f"Kvarvarande substantivmismatch: {summary['remaining_noun_mismatches']}")
    print(f"Orsakskategorier: {summary['cause_count']}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
