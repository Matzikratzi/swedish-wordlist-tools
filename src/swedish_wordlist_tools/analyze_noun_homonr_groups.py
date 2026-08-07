from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import _saol_upos
from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-homonr-groups.txt")
DEFAULT_JSON = Path("reports/saol14-noun-homonr-groups.json")

_SUP_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")


def clean_word(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return re.sub(r"\s+", " ", text).strip()


def article_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("urspr_lopnr") or ""), str(row.get("subnr") or "")


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    nouns = [row for row in records if _saol_upos(row) == "NOUN"]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in nouns:
        groups[article_key(row)].append(row)

    multi = {key: rows for key, rows in groups.items() if len(rows) > 1}
    pattern_counts: Counter[str] = Counter()
    pair01: list[dict[str, Any]] = []
    different_ord = 0
    same_norm = 0
    same_text = 0
    same_stycke = 0

    for key, rows in multi.items():
        homonrs = tuple(sorted({str(row.get("homonr") or "") for row in rows}))
        pattern_counts["{" + ",".join(homonrs) + "}"] += 1
        ords = sorted({clean_word(row.get("ord")) for row in rows if clean_word(row.get("ord"))}, key=str.casefold)
        norms = {clean_word(row.get("normaliserat_ord")).casefold() for row in rows}
        texts = {str(row.get("text") or "") for row in rows}
        stycken = {str(row.get("stycke") or "") for row in rows}
        if len(ords) > 1:
            different_ord += 1
        if len(norms) == 1:
            same_norm += 1
        if len(texts) == 1:
            same_text += 1
        if len(stycken) == 1:
            same_stycke += 1
        if set(homonrs) == {"0", "1"}:
            pair01.append({
                "urspr_lopnr": key[0],
                "subnr": key[1],
                "normaliserat_ord": str(rows[0].get("normaliserat_ord") or ""),
                "ord_variants": ords,
                "same_normaliserat_ord": len(norms) == 1,
                "same_text": len(texts) == 1,
                "same_stycke": len(stycken) == 1,
                "text": str(rows[0].get("text") or "") if len(texts) == 1 else None,
                "rows": [
                    {
                        "homonr": str(row.get("homonr") or ""),
                        "ord": str(row.get("ord") or ""),
                        "ord_clean": clean_word(row.get("ord")),
                    }
                    for row in rows
                ],
            })

    pair01.sort(key=lambda x: (str(x["normaliserat_ord"]).casefold(), str(x["subnr"])))
    clean_pair01 = [
        row for row in pair01
        if row["same_normaliserat_ord"] and row["same_text"] and row["same_stycke"] and len(row["ord_variants"]) > 1
    ]
    underscore_clean = [row for row in clean_pair01 if " _ " in str(row.get("text") or "")]

    return {
        "noun_rows": len(nouns),
        "article_groups": len(groups),
        "multirow_article_groups": len(multi),
        "multirow_groups_different_ord": different_ord,
        "multirow_groups_same_normalized": same_norm,
        "multirow_groups_same_text": same_text,
        "multirow_groups_same_stycke": same_stycke,
        "homonr_patterns": dict(sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))),
        "homonr_0_1_groups": len(pair01),
        "clean_variant_0_1_groups": len(clean_pair01),
        "clean_variant_0_1_groups_with_underscore": len(underscore_clean),
        "clean_variant_groups": clean_pair01,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        f"Substantivrader: {summary['noun_rows']}",
        f"Artikelgrupper (urspr_lopnr, subnr): {summary['article_groups']}",
        f"Artikelgrupper med flera rader: {summary['multirow_article_groups']}",
        f"Fler-radsgrupper med olika ord: {summary['multirow_groups_different_ord']}",
        f"Fler-radsgrupper med samma normaliserat_ord: {summary['multirow_groups_same_normalized']}",
        f"Fler-radsgrupper med samma text: {summary['multirow_groups_same_text']}",
        f"Fler-radsgrupper med samma stycke: {summary['multirow_groups_same_stycke']}",
        f"Grupper med homonr {{0,1}}: {summary['homonr_0_1_groups']}",
        f"Rena {{0,1}}-variantgrupper (samma normaliserat_ord/text/stycke, olika ord): {summary['clean_variant_0_1_groups']}",
        f"Varav med _-notation: {summary['clean_variant_0_1_groups_with_underscore']}",
        "",
        "Homonr-mönster:",
    ]
    for pattern, count in summary["homonr_patterns"].items():
        lines.append(f"{count:6d}  {pattern}")
    lines.extend(["", "Rena homonr {0,1}-variantgrupper:"])
    for row in summary["clean_variant_groups"]:
        lines.append(
            f"  {row['normaliserat_ord']} | subnr={row['subnr']} | ord={', '.join(row['ord_variants'])} | text={row.get('text') or '(null)'}"
        )
    if not summary["clean_variant_groups"]:
        lines.append("  (inga)")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SAOL14 noun article groups and homonr=0 variant rows")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(render(summary).split("\n\n", 1)[0])
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
