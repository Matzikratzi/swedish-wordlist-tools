from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .saol_row_interpreter import interpret_noun_row

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-singular-only-compound-heads.txt")
DEFAULT_JSON = Path("reports/saol14-singular-only-compound-heads.json")
SINGULAR_ONLY = {"+en", "+et", "+n", "+t"}
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: object) -> str:
    value = html.unescape(str(text or ""))
    value = _TAG_RE.sub("", value)
    return value.replace("·", "").strip()


def _head_from_stycke(stycke: object) -> str:
    value = _clean(stycke)
    if "|" not in value:
        return ""
    return value.rsplit("|", 1)[-1].strip()


def _has_explicit_plural(row: dict[str, Any]) -> bool:
    interpreted = interpret_noun_row(row)
    return interpreted is not None and any(form.slot == "pl_indef" for form in interpreted.key_forms)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def analyze(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    nouns = [row for row in rows if str(row.get("upos") or "").upper() == "NOUN"]
    by_lemma: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        lemma = str(row.get("normaliserat_ord") or "").casefold()
        if lemma:
            by_lemma[lemma].append(row)

    result: list[dict[str, Any]] = []
    for row in nouns:
        notation = str(row.get("text") or "").strip()
        if notation not in SINGULAR_ONLY:
            continue
        lemma = str(row.get("normaliserat_ord") or "")
        head = _head_from_stycke(row.get("stycke"))
        if not head or head.casefold() == lemma.casefold():
            continue
        head_rows = by_lemma.get(head.casefold(), [])
        plural_heads = [candidate for candidate in head_rows if _has_explicit_plural(candidate)]
        if not plural_heads:
            continue
        result.append({
            "lemma": lemma,
            "homonr": str(row.get("homonr") or ""),
            "notation": notation,
            "stycke": str(row.get("stycke") or ""),
            "head": head,
            "head_rows": [
                {
                    "homonr": str(candidate.get("homonr") or ""),
                    "notation": str(candidate.get("text") or ""),
                    "stycke": str(candidate.get("stycke") or ""),
                }
                for candidate in plural_heads
            ],
        })
    result.sort(key=lambda item: (item["head"].casefold(), item["lemma"].casefold(), item["homonr"]))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    head_counts = Counter(row["head"] for row in rows)
    notation_counts = Counter(row["notation"] for row in rows)
    return {
        "records": len(rows),
        "unique_heads": len(head_counts),
        "notation_counts": dict(notation_counts.most_common()),
        "top_heads": head_counts.most_common(50),
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: singular-only-sammansättningar vars efterled har explicit plural som eget uppslagsord",
        "",
        f"Poster: {summary['records']}",
        f"Unika efterleder: {summary['unique_heads']}",
        "",
        "Notationer hos sammansättningen:",
    ]
    for notation, count in summary["notation_counts"].items():
        lines.append(f"{count:5}  {notation}")
    lines.extend(["", "Vanligaste efterleder:"])
    for head, count in summary["top_heads"]:
        lines.append(f"{count:5}  {head}")
    lines.extend(["", "Exempel:"])
    for row in summary["rows"][:200]:
        head_desc = "; ".join(
            f"homonr={item['homonr'] or '-'} notation={item['notation']}"
            for item in row["head_rows"]
        )
        lines.append(
            f"  {row['lemma']} ({row['homonr'] or '-'}) | {row['notation']} | "
            f"efterled={row['head']} [{head_desc}] | stycke={row['stycke']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    rows = analyze(read_jsonl(args.input))
    summary = build_summary(rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print(f"Unika efterleder: {summary['unique_heads']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
