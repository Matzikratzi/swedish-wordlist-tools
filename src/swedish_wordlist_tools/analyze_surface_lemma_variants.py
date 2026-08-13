from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-surface-lemma-variants.txt")
DEFAULT_JSON = Path("reports/saol14-surface-lemma-variants.json")


def _difference_kind(normalized: str, written: str) -> str:
    if normalized == written:
        return "same"
    if normalized.casefold() == written.casefold():
        return "case_only"
    if normalized.replace("-", " ").casefold() == written.replace("-", " ").casefold():
        return "space_hyphen_only"
    return "different_spelling"


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    upos_counts: Counter[str] = Counter()
    raw_upos_counts: Counter[str] = Counter()
    ordkl_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()

    for record in records:
        normalized = clean_saol_word(record.get("normaliserat_ord"))
        written = clean_saol_word(record.get("ord"))
        if not normalized or not written or normalized == written:
            continue
        kind = _difference_kind(normalized, written)
        resolved_upos = _saol_upos(record)
        raw_upos = str(record.get("upos") or "")
        ordkl = str(record.get("ordkl") or "")
        row = {
            "normaliserat_ord": normalized,
            "ord": written,
            "kind": kind,
            "homonr": str(record.get("homonr") or ""),
            "record_id": str(record.get("subnr") or record.get("urspr_lopnr") or ""),
            "raw_upos": raw_upos,
            "resolved_upos": resolved_upos,
            "ordkl": ordkl,
            "text": str(record.get("text") or ""),
        }
        rows.append(row)
        kind_counts[kind] += 1
        upos_counts[resolved_upos] += 1
        raw_upos_counts[raw_upos] += 1
        ordkl_counts[ordkl] += 1

    rows.sort(key=lambda row: (row["kind"], row["normaliserat_ord"].casefold(), row["ord"].casefold(), row["homonr"]))
    examples_by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if len(examples_by_kind[row["kind"]]) < 80:
            examples_by_kind[row["kind"]].append(row)

    return {
        "records": len(rows),
        "kind_counts": dict(kind_counts.most_common()),
        "resolved_upos_counts": dict(upos_counts.most_common()),
        "raw_upos_counts": dict(raw_upos_counts.most_common()),
        "ordkl_counts": dict(ordkl_counts.most_common(40)),
        "examples_by_kind": dict(examples_by_kind),
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: städat ord jämfört med normaliserat_ord",
        "",
        "Endast typografiska markörer (·, |, mjukt bindestreck och markup) tas bort.",
        "Vanliga mellanslag och bindestreck bevaras som del av den skrivna ordformen.",
        "Rapporten är diagnostisk: den avgör inte automatiskt vilka varianter som ska ärva paradigm.",
        "",
        f"Poster där värdena skiljer sig: {summary['records']}",
        "Skillnadstyper: " + ", ".join(f"{key}={value}" for key, value in summary["kind_counts"].items()),
        "Resolverad UPOS: " + ", ".join(f"{key or '(tom)'}={value}" for key, value in summary["resolved_upos_counts"].items()),
        "Rå UPOS: " + ", ".join(f"{key or '(tom)'}={value}" for key, value in summary["raw_upos_counts"].items()),
        "",
        "Vanligaste ordkl:",
    ]
    for ordkl, count in summary["ordkl_counts"].items():
        lines.append(f"  {count:6}  {ordkl or '(tom)'}")

    for kind, rows in summary["examples_by_kind"].items():
        lines.extend(["", f"Exempel: {kind}"])
        for row in rows:
            lines.append(
                "  "
                + f"{row['normaliserat_ord']} -> {row['ord']}"
                + (f" | homonr={row['homonr']}" if row["homonr"] else "")
                + f" | upos={row['resolved_upos']}"
                + f" | ordkl={row['ordkl']}"
                + f" | text={row['text']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster där städat ord skiljer sig från normaliserat_ord: {summary['records']}")
    print("Skillnadstyper: " + ", ".join(f"{key}={value}" for key, value in summary["kind_counts"].items()))
    print("Resolverad UPOS: " + ", ".join(f"{key or '(tom)'}={value}" for key, value in summary["resolved_upos_counts"].items()))
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
