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
DEFAULT_TEXT = Path("reports/saol14-noun-ord-variants.txt")
DEFAULT_JSON = Path("reports/saol14-noun-ord-variants.json")

_SUP_ELEMENT_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _clean_display_form(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return re.sub(r"\s+", " ", text).strip()


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or "")


def _is_alternative_notation(record: dict[str, Any]) -> bool:
    return bool(re.search(r"\s_\s", str(record.get("text") or "")))


def analyze_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    nouns = [record for record in records if _saol_upos(record) == "NOUN"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in nouns:
        groups[_record_id(record)].append(record)

    ord_with_bar = [record for record in nouns if "|" in str(record.get("ord") or "")]
    stycke_with_bar = [record for record in nouns if "|" in str(record.get("stycke") or "")]
    ord_differs = [
        record
        for record in nouns
        if _clean_display_form(record.get("ord"))
        and _clean_display_form(record.get("ord")).casefold()
        != _clean_display_form(record.get("normaliserat_ord")).casefold()
    ]
    alternative_rows = [record for record in nouns if _is_alternative_notation(record)]

    candidate_groups: list[dict[str, Any]] = []
    for record_id, rows in groups.items():
        ord_variants = sorted(
            {
                _clean_display_form(row.get("ord"))
                for row in rows
                if _clean_display_form(row.get("ord"))
            },
            key=str.casefold,
        )
        if len(ord_variants) < 2 or not any(_is_alternative_notation(row) for row in rows):
            continue
        candidate_groups.append(
            {
                "record_id": record_id,
                "lemma": str(rows[0].get("normaliserat_ord") or ""),
                "notation": str(rows[0].get("text") or ""),
                "stycke_variants": sorted(
                    {str(row.get("stycke") or "") for row in rows}, key=str.casefold
                ),
                "ord_variants": ord_variants,
                "rows": [
                    {
                        "homonym_number": str(row.get("homonr") or ""),
                        "ord": str(row.get("ord") or ""),
                        "ord_clean": _clean_display_form(row.get("ord")),
                        "stycke": str(row.get("stycke") or ""),
                    }
                    for row in rows
                ],
            }
        )

    candidate_groups.sort(key=lambda row: (str(row["lemma"]).casefold(), str(row["record_id"])))
    notation_counts = Counter(str(row["notation"]) for row in candidate_groups)

    return {
        "noun_records": len(nouns),
        "noun_records_ord_with_bar": len(ord_with_bar),
        "noun_records_stycke_with_bar": len(stycke_with_bar),
        "noun_records_ord_differs_from_normalized": len(ord_differs),
        "noun_records_with_alternative_notation": len(alternative_rows),
        "candidate_record_groups": len(candidate_groups),
        "candidate_rows": sum(len(row["rows"]) for row in candidate_groups),
        "candidate_notation_counts": dict(sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))),
        "candidates": candidate_groups,
    }


def write_report(summary: dict[str, Any], text_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"Substantivposter: {summary['noun_records']}",
        f"Med lodstreck i ord: {summary['noun_records_ord_with_bar']}",
        f"Med lodstreck i stycke: {summary['noun_records_stycke_with_bar']}",
        f"ord skiljer sig från normaliserat_ord: {summary['noun_records_ord_differs_from_normalized']}",
        f"Med _-alternativ i notation: {summary['noun_records_with_alternative_notation']}",
        f"Kandidatgrupper med flera ord-baser + _-notation: {summary['candidate_record_groups']}",
        f"Kandidatrader: {summary['candidate_rows']}",
        "",
        "Kandidatnotationer:",
    ]
    counts = summary["candidate_notation_counts"]
    if counts:
        for notation, count in counts.items():
            lines.append(f"{count:6d}  {notation}")
    else:
        lines.append("  (inga)")

    lines.extend(["", "Kandidatgrupper:"])
    for row in summary["candidates"]:
        lines.append(
            f"  {row['lemma']} | record_id={row['record_id']} | notation={row['notation']}"
        )
        lines.append(f"    ord: {', '.join(row['ord_variants'])}")
        lines.append(f"    stycke: {', '.join(row['stycke_variants'])}")
    if not summary["candidates"]:
        lines.append("  (inga)")

    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit how SAOL14 noun ord/stycke variants interact with _ alternative notation"
        )
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze_records(read_jsonl(args.saol))
    write_report(summary, args.text, args.json)
    print(f"Substantivposter: {summary['noun_records']}")
    print(f"Med lodstreck i ord: {summary['noun_records_ord_with_bar']}")
    print(f"ord skiljer sig från normaliserat_ord: {summary['noun_records_ord_differs_from_normalized']}")
    print(f"Med _-alternativ i notation: {summary['noun_records_with_alternative_notation']}")
    print(f"Kandidatgrupper: {summary['candidate_record_groups']}")
    print(f"Kandidatrader: {summary['candidate_rows']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
