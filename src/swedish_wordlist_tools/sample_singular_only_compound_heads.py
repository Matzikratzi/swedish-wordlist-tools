from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_singular_only_compound_heads import analyze, read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-singular-only-compound-heads-sample.txt")
DEFAULT_JSON = Path("reports/saol14-singular-only-compound-heads-sample.json")

# Families chosen to test the hypothesis that SAOL article scope, rather than
# the compound head's paradigm, controls which forms should be generated.
TARGET_HEADS = (
    "aktivitet",
    "anslutning",
    "arbete",
    "ansvar",
    "bekämpning",
    "frihet",
    "skyldighet",
    "säkerhet",
    "produktion",
    "forskning",
    "brödraskap",
)


def sample(rows: Iterable[dict[str, Any]], per_head: int = 4) -> list[dict[str, Any]]:
    candidates = analyze(rows)
    by_head: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_head[row["head"].casefold()].append(row)

    selected: list[dict[str, Any]] = []
    for head in TARGET_HEADS:
        family = sorted(
            by_head.get(head.casefold(), []),
            key=lambda item: (item["lemma"].casefold(), item["homonr"]),
        )
        selected.extend(family[:per_head])
    return selected


def build_summary(rows: list[dict[str, Any]], per_head: int) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for head in TARGET_HEADS:
        counts[head] = sum(row["head"].casefold() == head.casefold() for row in rows)
    return {
        "purpose": "manual_svenska_se_scope_audit",
        "hypothesis": "compound article notation controls generated paradigm; plural is not inherited from the head",
        "per_head": per_head,
        "target_heads": list(TARGET_HEADS),
        "head_counts": counts,
        "records": len(rows),
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 stratifierat stickprov: singular-only-sammansättningar",
        "",
        "Syfte: kontrollera mot svenska.se att plural inte ska ärvas från efterleden.",
        f"Poster: {summary['records']}",
        "",
    ]
    current = None
    for row in summary["rows"]:
        if row["head"] != current:
            current = row["head"]
            head_desc = "; ".join(
                f"homonr={item['homonr'] or '-'} notation={item['notation']}"
                for item in row["head_rows"]
            )
            lines.extend([f"Efterled: {current} [{head_desc}]", ""])
        lines.append(
            f"  {row['lemma']} ({row['homonr'] or '-'}) | artikel={row['notation']} | stycke={row['stycke']}"
        )
    lines.extend([
        "",
        "Manuell kontroll per ord:",
        "  [ ] svenska.se visar endast de former som sammansättningens egen SAOL-notation anger",
        "  [ ] ingen plural visas när sammansättningen saknar pluralnotation",
        "  [ ] notera avvikelse om svenska.se faktiskt visar plural",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--per-head", type=int, default=4)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    rows = sample(read_jsonl(args.input), per_head=args.per_head)
    summary = build_summary(rows, args.per_head)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for head, count in summary["head_counts"].items():
        print(f"{head}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
