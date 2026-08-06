from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_JSON = Path("reports/saol14-k-markup.json")
DEFAULT_TEXT = Path("reports/saol14-k-markup.txt")

_K_TAG_RE = re.compile(r"</?k>", re.IGNORECASE)
_BALANCED_K_RE = re.compile(r"<k>.*?</k>", re.IGNORECASE | re.DOTALL)


def classify_k_markup(text: str) -> str | None:
    """Classify ``<k>`` markup without interpreting the marked text.

    ``None`` means that no k markup occurs. ``balanced`` means that removing
    complete ``<k>...</k>`` spans consumes every k tag. Anything else is
    malformed source markup.
    """

    if not _K_TAG_RE.search(text):
        return None
    remainder = _BALANCED_K_RE.sub("", text)
    return "malformed" if _K_TAG_RE.search(remainder) else "balanced"


def build_analysis(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    seen: set[tuple[str, str, str]] = set()

    for record in records:
        text = str(record.get("text", ""))
        classification = classify_k_markup(text)
        if classification is None:
            continue
        lemma = str(record.get("normaliserat_ord") or record.get("ord") or "")
        record_id = str(record.get("subnr") or record.get("urspr_lopnr") or record.get("id") or "")
        marker = (record_id, lemma, text)
        if marker in seen:
            continue
        seen.add(marker)
        counts[classification] += 1
        rows.append(
            {
                "record_id": record_id,
                "lemma": lemma,
                "homonym_number": str(record.get("homonr", "")),
                "upos": str(record.get("upos", "")),
                "classification": classification,
                "text": text,
                "source": str(record.get("source", "")),
            }
        )

    rows.sort(
        key=lambda row: (
            row["classification"] != "malformed",
            row["lemma"].casefold(),
            row["record_id"],
        )
    )
    return {
        "records_with_k_markup": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "rows": rows,
    }


def render_analysis(analysis: dict[str, Any]) -> str:
    counts = analysis["classification_counts"]
    lines = [
        f"Poster med <k>-markup: {analysis['records_with_k_markup']}",
        f"Balanserad markup: {counts.get('balanced', 0)}",
        f"Trasig markup: {counts.get('malformed', 0)}",
    ]
    for classification, heading in (
        ("malformed", "Trasig <k>-markup"),
        ("balanced", "Balanserad <k>-markup i text-fältet"),
    ):
        lines.extend(["", heading + ":"])
        for row in analysis["rows"]:
            if row["classification"] != classification:
                continue
            lines.append(
                f"  {row['lemma']} | homonr={row['homonym_number']} | "
                f"upos={row['upos']} | {row['text']}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory all SAOL14 records whose text field contains <k> markup"
    )
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    analysis = build_analysis(read_jsonl(args.source))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.text.write_text(render_analysis(analysis), encoding="utf-8")
    print(f"Poster med <k>-markup: {analysis['records_with_k_markup']}")
    print(
        "Klassningar: "
        + ", ".join(
            f"{key}={value}"
            for key, value in analysis["classification_counts"].items()
        )
    )
    print(f"Rapport: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
