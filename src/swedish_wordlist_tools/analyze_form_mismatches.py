from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSON = Path("reports/saol14-form-mismatches-summary.json")
DEFAULT_TEXT = Path("reports/saol14-form-mismatches.txt")
TARGET_STATUS = "form_set_mismatch"


def _suffixes(lemma: str, forms: Iterable[str]) -> tuple[str, ...]:
    lemma_folded = lemma.casefold()
    result: list[str] = []
    for form in forms:
        folded = str(form).casefold()
        if lemma_folded and folded.startswith(lemma_folded):
            result.append("+" + folded[len(lemma_folded) :])
        else:
            result.append("=" + folded)
    return tuple(sorted(result))


def analyse_rows(rows: Iterable[dict[str, Any]], examples: int = 10) -> dict[str, Any]:
    selected = [row for row in rows if row.get("status") == TARGET_STATUS]
    upos_counts = Counter(str(row.get("upos", "")) for row in selected)
    notation_counts = Counter(str(row.get("notation", "")) for row in selected)
    method_counts = Counter(str(row.get("match_method", "")) for row in selected)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        lemma = str(row.get("lemma", ""))
        key = (
            str(row.get("upos", "")),
            str(row.get("notation", "")),
            str(row.get("match_method", "")),
            _suffixes(lemma, row.get("extra_from_saol", [])),
            _suffixes(lemma, row.get("missing_from_saol", [])),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for (upos, notation, method, extra, missing), members in grouped.items():
        members.sort(key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("homonym_number", ""))))
        groups.append({
            "upos": upos,
            "notation": notation,
            "match_method": method,
            "count": len(members),
            "extra_pattern": list(extra),
            "missing_pattern": list(missing),
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
        })

    groups.sort(key=lambda group: (-int(group["count"]), str(group["upos"]), str(group["notation"]), str(group["match_method"])))
    return {
        "status": TARGET_STATUS,
        "records": len(selected),
        "upos_counts": dict(sorted(upos_counts.items(), key=lambda item: (-item[1], item[0]))),
        "notation_counts": dict(sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))),
        "match_method_counts": dict(sorted(method_counts.items(), key=lambda item: (-item[1], item[0]))),
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
    lines = [f"Poster: {summary['records']}"]
    for heading, key in (
        ("Per ordklass:", "upos_counts"),
        ("Per SAOL-notation:", "notation_counts"),
        ("Per matchningsmetod:", "match_method_counts"),
    ):
        lines.extend(["", heading])
        for value, count in summary[key].items():
            lines.append(f"{count:5}  {value or '(tomt)'}")

    lines.extend(["", "Grupper efter formskillnad:"])
    for index, group in enumerate(summary["groups"], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        lines.extend([
            "",
            f"{index}. {group['upos']} | {group['notation']} | {group['match_method']} — {group['count']} poster",
            "   Extra från SAOL: " + (", ".join(group["extra_pattern"]) or "–"),
            "   Saknas från SAOL: " + (", ".join(group["missing_pattern"]) or "–"),
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
    parser = argparse.ArgumentParser(description="Gruppera kvarvarande formmismatch efter ordklass, notation och formmönster")
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
    print(f"Kvarvarande formmismatch: {summary['records']}")
    for upos, count in summary["upos_counts"].items():
        print(f"{upos}: {count}")
    print(f"Grupper: {len(summary['groups'])}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
