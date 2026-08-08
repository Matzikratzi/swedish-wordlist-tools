from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-unique-form-match-audit.txt")
DEFAULT_JSON = Path("reports/saol14-unique-form-match-audit.json")
TARGET_METHOD = "unique_form_same_upos"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _fold(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def analyze(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("match_method") or "") != TARGET_METHOD:
            continue
        generated = _fold(row.get("generated_forms", ()))
        saldo = _fold(row.get("saldo_forms", ()))
        overlap = generated & saldo
        union = generated | saldo
        selected.append(
            {
                "lemma": str(row.get("lemma") or ""),
                "homonym_number": str(row.get("homonym_number") or ""),
                "upos": str(row.get("upos") or ""),
                "status": str(row.get("status") or ""),
                "paradigm_status": str(row.get("paradigm_status") or ""),
                "saldo_lemmas": list(row.get("saldo_lemmas", ())),
                "generated_count": len(generated),
                "saldo_count": len(saldo),
                "overlap_count": len(overlap),
                "overlap_forms": sorted(overlap),
                "jaccard": (len(overlap) / len(union)) if union else 1.0,
                "generated_forms": sorted(generated),
                "saldo_forms": sorted(saldo),
            }
        )

    overlap_counts = Counter(row["overlap_count"] for row in selected)
    status_counts = Counter(row["status"] for row in selected)
    paradigm_counts = Counter(row["paradigm_status"] for row in selected)
    low = [row for row in selected if row["overlap_count"] <= 1]
    low.sort(key=lambda row: (row["overlap_count"], row["jaccard"], row["lemma"].casefold()))
    return {
        "records": len(selected),
        "overlap_counts": dict(sorted(overlap_counts.items())),
        "status_counts": dict(sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))),
        "paradigm_status_counts": dict(sorted(paradigm_counts.items(), key=lambda item: (-item[1], item[0]))),
        "low_overlap_records": len(low),
        "low_overlap": low,
    }


def render_text(summary: dict[str, Any], examples: int = 80) -> str:
    lines = [
        "SAOL14 audit: unique_form_same_upos",
        "",
        f"Poster: {summary['records']}",
        f"Poster med overlap <= 1: {summary['low_overlap_records']}",
        "",
        "Överlapp (antal gemensamma former):",
    ]
    for count, records in summary["overlap_counts"].items():
        lines.append(f"  {count}: {records}")
    lines.extend(["", "Status:"])
    for name, count in summary["status_counts"].items():
        lines.append(f"  {count:4}  {name}")
    lines.extend(["", "Paradigmstatus:"])
    for name, count in summary["paradigm_status_counts"].items():
        lines.append(f"  {count:4}  {name or '(saknas)'}")
    lines.extend(["", "Lågt överlapp (första poster):"])
    for row in summary["low_overlap"][:examples]:
        saldo_lemmas = ", ".join(row["saldo_lemmas"]) or "–"
        overlap = ", ".join(row["overlap_forms"]) or "–"
        lines.append(
            f"  {row['lemma']} ({row['homonym_number']}) upos={row['upos']} "
            f"overlap={row['overlap_count']} jaccard={row['jaccard']:.3f} "
            f"SALDO-lemma={saldo_lemmas} gemensamt={overlap}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditera unique_form_same_upos-fallbacken")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print(f"Poster med overlap <= 1: {summary['low_overlap_records']}")
    for overlap, count in summary["overlap_counts"].items():
        print(f"overlap={overlap}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
