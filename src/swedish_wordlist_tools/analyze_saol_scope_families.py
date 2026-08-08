from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("reports/saol14-saldo-forms-beyond-saol-scope.jsonl")
DEFAULT_TEXT = Path("reports/saol14-saldo-forms-beyond-saol-scope-families.txt")
DEFAULT_JSON = Path("reports/saol14-saldo-forms-beyond-saol-scope-families.json")

FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("-ering/-isering/-ifiering", ("ering", "isering", "ifiering")),
    ("-ning", ("ning",)),
    ("-ism", ("ism",)),
    ("-itet", ("itet",)),
    ("-tion/-sion", ("tion", "sion")),
    ("-het", ("het",)),
    ("-skap", ("skap",)),
    ("-ande/-ende", ("ande", "ende")),
    ("-ologi/-nomi/-fobi", ("ologi", "nomi", "fobi")),
    ("-i", ("i",)),
]


def family_for(lemma: str) -> str:
    folded = lemma.casefold()
    for name, endings in FAMILIES:
        if folded.endswith(endings):
            return name
    return "övrigt"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[family_for(str(row.get("lemma") or ""))].append(row)
    ordered = sorted(by_family.items(), key=lambda item: (-len(item[1]), item[0]))
    result: dict[str, Any] = {"records": len(rows), "families": []}
    for family, members in ordered:
        notation_counts = Counter(str(row.get("notation") or "") for row in members)
        pattern_counts = Counter(tuple(row.get("saldo_only_relative", ())) for row in members)
        examples = [str(row.get("lemma") or "") for row in members[:20]]
        result["families"].append({
            "family": family,
            "count": len(members),
            "notation_counts": dict(notation_counts.most_common()),
            "saldo_extra_patterns": [
                {"pattern": list(pattern), "count": count}
                for pattern, count in pattern_counts.most_common(8)
            ],
            "examples": examples,
        })
    return result


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 paradigmomfång: morfologiska familjer",
        "",
        f"Poster: {summary['records']}",
        "",
    ]
    for item in summary["families"]:
        lines.extend([
            f"{item['family']}: {item['count']}",
            "  notationer: " + ", ".join(f"{k}={v}" for k, v in item["notation_counts"].items()),
            "  exempel: " + ", ".join(item["examples"]),
            "  största SALDO-extra:",
        ])
        for pattern in item["saldo_extra_patterns"]:
            lines.append(f"    {pattern['count']:5}  {', '.join(pattern['pattern'])}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = build(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print(f"Familjer: {len(summary['families'])}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
