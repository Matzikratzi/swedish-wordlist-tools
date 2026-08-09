from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .saol_row_interpreter import interpret_noun_row

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-null-noun-ordkl.txt")
DEFAULT_JSON = Path("reports/saol14-null-noun-ordkl.json")

_NULL_NOTATIONS = frozenset({"", "(null)", "null"})


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _is_null_notation(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _NULL_NOTATIONS


def _ordkl_interpretable(row: dict[str, Any]) -> bool:
    interpreted = interpret_noun_row(
        {
            "upos": "NOUN",
            "normaliserat_ord": str(row.get("lemma") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "text": None,
        }
    )
    return interpreted is not None and interpreted.pattern.startswith("(ordkl:")


def candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        if str(row.get("status") or "") != "form_set_mismatch":
            continue
        if not _is_null_notation(row.get("notation")):
            continue

        result.append(
            {
                "lemma": str(row.get("lemma") or ""),
                "homonym_number": str(row.get("homonym_number") or ""),
                "record_id": str(row.get("record_id") or ""),
                "ordkl": str(row.get("ordkl") or "").strip(),
                "notation": row.get("notation"),
                "match_method": str(row.get("match_method") or ""),
                "generated_forms": [str(value) for value in row.get("generated_forms", ())],
                "saldo_forms": [str(value) for value in row.get("saldo_forms", ())],
                "ordkl_interpretable": _ordkl_interpretable(row),
            }
        )
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["ordkl"]].append(row)

    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "ordkl_groups": len(groups),
        "ordkl_interpretable": sum(bool(row["ordkl_interpretable"]) for row in rows),
        "groups": [
            {
                "ordkl": ordkl,
                "count": len(members),
                "ordkl_interpretable": sum(bool(member["ordkl_interpretable"]) for member in members),
                "match_methods": dict(Counter(member["match_method"] for member in members).most_common()),
                "examples": [
                    {
                        "lemma": member["lemma"],
                        "homonym_number": member["homonym_number"],
                        "record_id": member["record_id"],
                        "generated_forms": member["generated_forms"],
                        "saldo_forms": member["saldo_forms"],
                        "ordkl_interpretable": member["ordkl_interpretable"],
                    }
                    for member in members[:20]
                ],
            }
            for ordkl, members in ordered
        ],
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: form_set_mismatch med text=(null), grupperade efter ordkl",
        "",
        "Syftet är att behandla ordkl som möjlig paradigmbärare när text saknas,",
        "inte att automatiskt tolka text=(null) som saknad böjningsinformation.",
        "",
        f"Poster: {summary['records']}",
        f"ordkl-grupper: {summary['ordkl_groups']}",
        f"Redan tolkbara via ordkl: {summary['ordkl_interpretable']}",
        "",
        "Grupper:",
    ]
    for index, group in enumerate(summary["groups"], start=1):
        ordkl = group["ordkl"] or "(tom ordkl)"
        lines.append("")
        lines.append(
            f"{index}. {group['count']} | {ordkl} | "
            f"tolkbara via ordkl={group['ordkl_interpretable']}"
        )
        if group["match_methods"]:
            lines.append(
                "   Matchmetoder: "
                + ", ".join(f"{key or '(tomt)'}={value}" for key, value in group["match_methods"].items())
            )
        examples = ", ".join(
            example["lemma"]
            + (f" ({example['homonym_number']})" if example["homonym_number"] else "")
            for example in group["examples"][:12]
        )
        if examples:
            lines.append(f"   Exempel: {examples}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = build_summary(candidates(read_jsonl(args.input)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Poster: {summary['records']}")
    print(f"ordkl-grupper: {summary['ordkl_groups']}")
    print(f"Redan tolkbara via ordkl: {summary['ordkl_interpretable']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
