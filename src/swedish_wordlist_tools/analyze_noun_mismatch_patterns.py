from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSON = Path("reports/saol14-noun-mismatch-patterns.json")
DEFAULT_TEXT = Path("reports/saol14-noun-mismatch-patterns.txt")


def _suffix_pattern(lemma: str, forms: Iterable[str]) -> tuple[str, ...]:
    folded_lemma = lemma.casefold()
    result: list[str] = []
    for value in forms:
        form = str(value).casefold()
        if folded_lemma and form.startswith(folded_lemma):
            result.append("+" + form[len(folded_lemma) :])
        else:
            result.append("=" + form)
    return tuple(sorted(result))


def analyse_rows(rows: Iterable[dict[str, Any]], examples: int = 10) -> dict[str, Any]:
    all_rows = list(rows)
    mismatches = [row for row in all_rows if row.get("status") == "form_set_mismatch"]
    nouns = [row for row in mismatches if row.get("upos") == "NOUN"]

    grouped: dict[tuple[tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        lemma = str(row.get("lemma", ""))
        key = (
            _suffix_pattern(lemma, row.get("extra_from_saol", [])),
            _suffix_pattern(lemma, row.get("missing_from_saol", [])),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for (extra, missing), members in grouped.items():
        members.sort(key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("homonym_number", ""))))
        groups.append({
            "count": len(members),
            "extra_pattern": list(extra),
            "missing_pattern": list(missing),
            "notation_counts": dict(Counter(str(row.get("notation", "")) for row in members).most_common()),
            "match_method_counts": dict(Counter(str(row.get("match_method", "")) for row in members).most_common()),
            "multiple_saol_homonyms": sum(1 for row in members if row.get("matching_saol_homonyms")),
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

    groups.sort(key=lambda group: (-int(group["count"]), group["extra_pattern"], group["missing_pattern"]))
    status_counts = Counter(str(row.get("status", "")) for row in all_rows)
    return {
        "validated_records": len(all_rows),
        "remaining_form_mismatches_total": len(mismatches),
        "remaining_noun_form_mismatches": len(nouns),
        "remaining_non_noun_form_mismatches": len(mismatches) - len(nouns),
        "noun_mismatch_groups": len(groups),
        "status_counts": dict(sorted(status_counts.items())),
        "groups": groups,
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


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Validerade poster: {summary['validated_records']}",
        f"Kvarvarande formmismatch totalt: {summary['remaining_form_mismatches_total']}",
        f"Kvarvarande substantivmismatch: {summary['remaining_noun_form_mismatches']}",
        f"Kvarvarande övriga formmismatch: {summary['remaining_non_noun_form_mismatches']}",
        f"Substantivgrupper efter formskillnad: {summary['noun_mismatch_groups']}",
        "",
        "Största substantivgrupperna:",
    ]
    for index, group in enumerate(summary["groups"], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        notations = ", ".join(f"{value} ({count})" for value, count in list(group["notation_counts"].items())[:8])
        methods = ", ".join(f"{value} ({count})" for value, count in group["match_method_counts"].items())
        lines.extend([
            "",
            f"{index}. {group['count']} poster",
            "   Extra från SAOL: " + (", ".join(group["extra_pattern"]) or "–"),
            "   Saknas från SAOL: " + (", ".join(group["missing_pattern"]) or "–"),
            "   Notationer: " + (notations or "–"),
            "   Matchning: " + (methods or "–"),
            f"   Redan markerade alternativa homonymer: {group['multiple_saol_homonyms']}",
            "   Exempel: " + examples,
        ])
    return "\n".join(lines) + "\n"


def analyse_file(input_path: Path = DEFAULT_INPUT, json_path: Path = DEFAULT_JSON, text_path: Path = DEFAULT_TEXT, examples: int = 10) -> dict[str, Any]:
    summary = analyse_rows(read_jsonl(input_path), examples)
    summary.update({"input": str(input_path), "json": str(json_path), "text": str(text_path)})
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gruppera kvarvarande substantivmismatch efter faktisk formskillnad")
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
    print(f"Kvarvarande formmismatch totalt: {summary['remaining_form_mismatches_total']}")
    print(f"Kvarvarande substantivmismatch: {summary['remaining_noun_form_mismatches']}")
    print(f"Substantivgrupper: {summary['noun_mismatch_groups']}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
