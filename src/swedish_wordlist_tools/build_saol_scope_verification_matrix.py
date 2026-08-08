from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DEFAULT_SAMPLE = Path("reports/saol14-singular-only-compound-heads-sample.json")
DEFAULT_CSV = Path("reports/saol14-singular-only-compound-heads-verification.csv")

MANUAL_VERIFIED = {
    "hyperaktivitet": {
        "svenska_se_2026": "singular_only",
        "note": "User supplied 2026 SAOL article: only singular table shown.",
    },
    "kyrkofrid": {
        "svenska_se_2026": "singular_only",
        "note": "User supplied 2026 SAOL article: only singular table shown.",
    },
    "fostbrödraskap": {
        "svenska_se_2026": "singular_only",
        "note": "User reported no plural in SAOL14 faksimil or 2026 svenska.se.",
    },
}


def build_rows(sample: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in sample.get("rows", []):
        lemma = str(item.get("lemma") or "")
        verification = MANUAL_VERIFIED.get(lemma, {})
        head_notation = "; ".join(
            str(head.get("notation") or "") for head in item.get("head_rows", [])
        )
        rows.append({
            "lemma": lemma,
            "compound_notation": str(item.get("notation") or ""),
            "head": str(item.get("head") or ""),
            "head_notation": head_notation,
            "stycke": str(item.get("stycke") or ""),
            "svenska_se_2026": str(verification.get("svenska_se_2026") or "unchecked"),
            "note": str(verification.get("note") or ""),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", nargs="?", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    rows = build_rows(sample)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "lemma", "compound_notation", "head", "head_notation", "stycke",
            "svenska_se_2026", "note",
        ])
        writer.writeheader()
        writer.writerows(rows)
    verified = sum(row["svenska_se_2026"] != "unchecked" for row in rows)
    print(f"Poster: {len(rows)}")
    print(f"Verifierade: {verified}")
    print(f"Kvar: {len(rows) - verified}")
    print(f"CSV: {args.csv}")


if __name__ == "__main__":
    main()
