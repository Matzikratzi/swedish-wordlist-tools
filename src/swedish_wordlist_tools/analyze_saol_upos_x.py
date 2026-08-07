from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-upos-x-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-upos-x-analysis.json")


def _is_nullish(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in {"", "(null)", "null", "none"}


def _classify_zero_context(record: dict[str, Any], group: list[dict[str, Any]]) -> str:
    if str(record.get("homonr") or "") != "0":
        return "not_zero"
    nonzero = [str(row.get("homonr") or "") for row in group if str(row.get("homonr") or "") not in {"", "0"}]
    if nonzero:
        return "article_variant_zero"
    ordkl = str(record.get("ordkl") or "").strip().casefold()
    if ordkl == "(hv)" and _is_nullish(record.get("text")):
        return "reference_entry_zero"
    return "standalone_zero_other"


def analyze(records: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = list(records)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("urspr_lopnr") or ""), str(row.get("subnr") or ""))].append(row)

    x_rows: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "X":
            continue
        key = (str(row.get("urspr_lopnr") or ""), str(row.get("subnr") or ""))
        x_rows.append({
            "normaliserat_ord": str(row.get("normaliserat_ord") or ""),
            "ord": str(row.get("ord") or ""),
            "stycke": str(row.get("stycke") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "text": str(row.get("text") or ""),
            "homonr": str(row.get("homonr") or ""),
            "urspr_lopnr": str(row.get("urspr_lopnr") or ""),
            "subnr": str(row.get("subnr") or ""),
            "zero_context": _classify_zero_context(row, grouped[key]),
        })

    ordkl_counts = Counter(row["ordkl"] for row in x_rows)
    homonr_counts = Counter(row["homonr"] for row in x_rows)
    text_counts = Counter(row["text"] for row in x_rows)
    zero_context_counts = Counter(row["zero_context"] for row in x_rows)
    ordkl_homonr_counts = Counter((row["ordkl"], row["homonr"]) for row in x_rows)
    ordkl_zero_context_counts = Counter((row["ordkl"], row["zero_context"]) for row in x_rows)

    hv_rows = [row for row in x_rows if row["ordkl"].strip().casefold() == "(hv)"]
    non_hv_rows = [row for row in x_rows if row["ordkl"].strip().casefold() != "(hv)"]

    summary = {
        "x_rows": len(x_rows),
        "x_unique_normalised_words": len({row["normaliserat_ord"] for row in x_rows}),
        "ordkl_counts": dict(ordkl_counts.most_common()),
        "homonr_counts": dict(homonr_counts.most_common()),
        "text_counts": dict(text_counts.most_common(50)),
        "zero_context_counts": dict(zero_context_counts.most_common()),
        "hv_rows": len(hv_rows),
        "non_hv_rows": len(non_hv_rows),
        "ordkl_homonr_counts": [
            {"ordkl": ordkl, "homonr": homonr, "count": count}
            for (ordkl, homonr), count in ordkl_homonr_counts.most_common()
        ],
        "ordkl_zero_context_counts": [
            {"ordkl": ordkl, "zero_context": context, "count": count}
            for (ordkl, context), count in ordkl_zero_context_counts.most_common()
        ],
    }
    return summary, x_rows


def render(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"UPOS=X-rader: {summary['x_rows']}",
        f"Unika normaliserade ord: {summary['x_unique_normalised_words']}",
        f"(hv)-rader: {summary['hv_rows']}",
        f"Övriga X-rader: {summary['non_hv_rows']}",
        "",
        "Ordkl inom UPOS=X:",
    ]
    for key, count in list(summary["ordkl_counts"].items())[:50]:
        lines.append(f"  {count:5d}  {key}")
    lines.extend(["", "Homonr inom UPOS=X:"])
    for key, count in summary["homonr_counts"].items():
        lines.append(f"  {count:5d}  {key}")
    lines.extend(["", "homonr=0-kontext inom UPOS=X:"])
    for key, count in summary["zero_context_counts"].items():
        lines.append(f"  {count:5d}  {key}")

    lines.extend(["", "Kombinationer ordkl × homonr:"])
    for item in summary["ordkl_homonr_counts"][:50]:
        lines.append(f"  {item['count']:5d}  {item['ordkl']} | homonr={item['homonr']}")

    lines.extend(["", "Kombinationer ordkl × nollkontext:"])
    for item in summary["ordkl_zero_context_counts"][:50]:
        lines.append(f"  {item['count']:5d}  {item['ordkl']} | {item['zero_context']}")

    def emit_examples(title: str, selected: list[dict[str, Any]], limit: int = 80) -> None:
        lines.extend(["", f"{title} ({len(selected)}):"])
        for row in selected[:limit]:
            lines.append(
                "  "
                + f"ord={row['ord']} | normaliserat={row['normaliserat_ord']} | "
                + f"ordkl={row['ordkl']} | homonr={row['homonr']} | text={row['text']} | "
                + f"id={row['urspr_lopnr']} | {row['zero_context']}"
            )

    emit_examples("X-rader med (hv)", [row for row in rows if row["ordkl"].strip().casefold() == "(hv)"])
    emit_examples("X-rader som inte är (hv)", [row for row in rows if row["ordkl"].strip().casefold() != "(hv)"])
    emit_examples("Fristående X-hänvisningar", [row for row in rows if row["zero_context"] == "reference_entry_zero"])
    emit_examples("X med homonr=0 men annan struktur", [row for row in rows if row["homonr"] == "0" and row["zero_context"] != "reference_entry_zero"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analysera vad UPOS=X betyder i SAOL14-exporten")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary, rows = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary, rows), encoding="utf-8")
    args.json.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"UPOS=X-rader: {summary['x_rows']}")
    print(f"(hv): {summary['hv_rows']}")
    print(f"Övriga X: {summary['non_hv_rows']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
