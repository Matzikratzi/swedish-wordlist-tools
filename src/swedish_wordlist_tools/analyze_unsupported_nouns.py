from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .saol_source_policy import is_truncated_inflection_source

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-unsupported-nouns.txt")
DEFAULT_JSON = Path("reports/saol14-unsupported-nouns.json")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("upos") or "").upper() == "NOUN"
        and str(row.get("status") or "") == "saol_pattern_unsupported"
        and not is_truncated_inflection_source(row)
    ]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = select(rows)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        notation = str(row.get("notation") or "(null)")
        groups[notation].append(row)

    grouped = []
    for notation, items in groups.items():
        ordkl = Counter(str(row.get("ordkl") or "") for row in items)
        generators = Counter(str(row.get("generator") or "") for row in items)
        examples = []
        seen = set()
        for row in items:
            lemma = str(row.get("lemma") or "")
            homonym = str(row.get("homonym_number") or "")
            marker = (lemma, homonym)
            if marker in seen:
                continue
            seen.add(marker)
            examples.append({"lemma": lemma, "homonym_number": homonym})
            if len(examples) >= 20:
                break
        grouped.append(
            {
                "notation": notation,
                "count": len(items),
                "ordkl": dict(ordkl.most_common()),
                "generators": dict(generators.most_common()),
                "examples": examples,
            }
        )
    grouped.sort(key=lambda item: (-int(item["count"]), str(item["notation"])))

    return {
        "records": len(selected),
        "notations": len(groups),
        "generator_counts": dict(Counter(str(row.get("generator") or "") for row in selected).most_common()),
        "groups": grouped,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: poster med saol_pattern_unsupported",
        "",
        "Detta är separat från form_set_mismatch. Rapporten visar vilka NOUN-rader",
        "som ännu inte har ett tolkbart/materialiserat SAOL-paradigm i valideringen.",
        "50-teckenstrunkerade källrader ligger i source_text_truncated och tas inte",
        "med här. Ingen SALDO-avvikelse används för att skapa grupperna.",
        "",
        f"Poster: {summary['records']}",
        f"Notationer: {summary['notations']}",
        "Generatorer: " + ", ".join(f"{key or '(tom)'}={value}" for key, value in summary["generator_counts"].items()),
        "",
        "Största notationer:",
        "",
    ]
    for index, group in enumerate(summary["groups"], 1):
        lines.append(f"{index}. {group['count']} | {group['notation']}")
        lines.append(
            "   Generatorer: "
            + ", ".join(f"{key or '(tom)'}={value}" for key, value in group["generators"].items())
        )
        lines.append(
            "   ordkl: "
            + ", ".join(f"{key or '(tom)'}={value}" for key, value in group["ordkl"].items())
        )
        examples = ", ".join(
            f"{item['lemma']} ({item['homonym_number']})" for item in group["examples"]
        )
        lines.append(f"   Exempel: {examples}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = summarize(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Poster: {summary['records']}")
    print(f"Notationer: {summary['notations']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
