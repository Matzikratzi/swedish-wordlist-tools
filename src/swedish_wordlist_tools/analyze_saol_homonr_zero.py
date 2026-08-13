from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-homonr-zero-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-homonr-zero-analysis.json")


def _id_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("urspr_lopnr") or ""), str(row.get("subnr") or ""))


def _is_reference_like(row: dict[str, Any]) -> bool:
    ordkl = str(row.get("ordkl") or "").strip().casefold()
    text = str(row.get("text") or "").strip().casefold()
    return ordkl == "(hv)" or (text in {"", "(null)", "null"} and not str(row.get("upos") or "").strip())


def classify(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = list(records)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_id_key(row)].append(row)

    output: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    anchor_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()

    for row in rows:
        if str(row.get("homonr") or "") != "0":
            continue
        peers = grouped[_id_key(row)]
        nonzero = [peer for peer in peers if str(peer.get("homonr") or "") not in {"", "0"}]
        anchors = sorted({str(peer.get("homonr") or "") for peer in nonzero})
        reference_like = _is_reference_like(row)

        if nonzero:
            classification = "article_variant"
        elif reference_like:
            classification = "reference_entry"
        else:
            classification = "standalone_zero_other"

        normalised = str(row.get("normaliserat_ord") or "")
        if classification == "reference_entry" and normalised:
            target_counts[normalised] += 1

        for anchor in anchors or ["none"]:
            anchor_counts[anchor] += 1
        class_counts[classification] += 1

        output.append({
            "classification": classification,
            "normaliserat_ord": normalised,
            "ord": str(row.get("ord") or ""),
            "stycke": str(row.get("stycke") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "text": str(row.get("text") or ""),
            "upos": str(row.get("upos") or ""),
            "urspr_lopnr": str(row.get("urspr_lopnr") or ""),
            "subnr": str(row.get("subnr") or ""),
            "anchor_homonr": anchors,
            "same_id_group_size": len(peers),
            "same_id_nonzero_count": len(nonzero),
        })

    output.sort(key=lambda item: (item["classification"], item["normaliserat_ord"].casefold(), item["ord"].casefold()))
    summary = {
        "homonr_zero_rows": len(output),
        "classification_counts": dict(sorted(class_counts.items())),
        "anchor_homonr_counts": dict(sorted(anchor_counts.items(), key=lambda kv: kv[0])),
        "reference_targets_with_multiple_rows": sum(1 for count in target_counts.values() if count > 1),
        "top_reference_targets": [
            {"normaliserat_ord": lemma, "rows": count}
            for lemma, count in target_counts.most_common(50)
        ],
    }
    return output, summary


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"homonr=0-rader: {summary['homonr_zero_rows']}",
        f"Klassningar: {summary['classification_counts']}",
        f"Ankar-homonr: {summary['anchor_homonr_counts']}",
        f"Hänvisningsmål med flera homonr=0-rader: {summary['reference_targets_with_multiple_rows']}",
        "",
    ]
    headings = [
        ("article_variant", "Variantrader inom samma artikel-ID"),
        ("reference_entry", "Fristående hänvisningsposter"),
        ("standalone_zero_other", "Övriga fristående homonr=0"),
    ]
    for classification, heading in headings:
        selected = [row for row in rows if row["classification"] == classification]
        lines.append(f"{heading} ({len(selected)}):")
        for row in selected[:150]:
            anchors = ",".join(row["anchor_homonr"]) or "–"
            lines.append(
                f"  {row['ord']} -> {row['normaliserat_ord']} | id={row['urspr_lopnr']} | "
                f"anchor={anchors} | ordkl={row['ordkl']} | text={row['text']}"
            )
        lines.append("")

    lines.append("Vanligaste hänvisningsmål med flera rader:")
    for item in summary["top_reference_targets"]:
        if item["rows"] <= 1:
            continue
        lines.append(f"  {item['normaliserat_ord']}: {item['rows']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Klassificera alla homonr=0-rader i SAOL14-exporten")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    rows, summary = classify(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows, summary), encoding="utf-8")
    args.json.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"homonr=0-rader: {summary['homonr_zero_rows']}")
    print(f"Klassningar: {summary['classification_counts']}")
    print(f"Ankar-homonr: {summary['anchor_homonr_counts']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
