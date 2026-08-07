from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_article_headings import is_plain_reference

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-heading-format-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-heading-format-analysis.json")

_SUP_RE = re.compile(r"^\s*<sup>\s*(\d+)\s*</sup>\s*", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_heading(value: str) -> dict[str, Any]:
    raw = str(value or "")
    match = _SUP_RE.match(raw)
    explicit_homonym = match.group(1) if match else None
    without_sup = raw[match.end():] if match else raw
    plain = html.unescape(_TAG_RE.sub("", without_sup)).strip()
    lexical = plain.replace("·", "").replace("|", "")
    return {
        "raw": raw,
        "explicit_homonym": explicit_homonym,
        "without_sup": without_sup.strip(),
        "plain": plain,
        "lexical": lexical,
    }


def _strip_html(value: str) -> str:
    return html.unescape(_TAG_RE.sub("", str(value or ""))).strip()


def classify_reference(row: dict[str, Any]) -> str:
    ordkl = _strip_html(str(row.get("ordkl") or "")).casefold()
    if not ordkl.startswith("(hv)"):
        return "not_reference"
    annotation = ordkl[len("(hv)"):].strip(" .;:")
    if not annotation:
        return "plain_reference"
    if any(token in annotation for token in ("komp", "superl")):
        return "inflection_reference"
    if any(token in annotation for token in ("+", "pl.", "best.", "pres.", "imper.", "perf.")):
        return "morphology_annotated_reference"
    return "other_annotated_reference"


def _ord_stycke_relation(row: dict[str, Any]) -> str:
    ord_value = str(row.get("ord") or "")
    stycke = str(row.get("stycke") or "")
    if not ord_value and not stycke:
        return "both_missing"
    if not ord_value or not stycke:
        return "one_missing"
    if ord_value == stycke:
        return "exact"
    ord_parsed = parse_heading(ord_value)
    stycke_parsed = parse_heading(stycke)
    if ord_parsed["without_sup"] == stycke_parsed["without_sup"]:
        return "differs_only_superscript"
    if ord_parsed["plain"] == stycke_parsed["plain"]:
        return "same_plain_text"
    if ord_parsed["lexical"] == stycke_parsed["lexical"]:
        return "same_lexical_text"
    if ord_parsed["lexical"].casefold() == stycke_parsed["lexical"].casefold():
        return "case_only_after_markup"
    return "different"


def analyze(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = list(records)
    relation_counts: Counter[str] = Counter()
    reference_counts: Counter[str] = Counter()
    explicit_sup_counts: Counter[str] = Counter()
    sup_mismatch: list[dict[str, Any]] = []
    relation_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reference_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        relation = _ord_stycke_relation(row)
        relation_counts[relation] += 1
        if relation != "exact" and len(relation_examples[relation]) < 30:
            relation_examples[relation].append({
                "ord": str(row.get("ord") or ""),
                "stycke": str(row.get("stycke") or ""),
                "normaliserat_ord": str(row.get("normaliserat_ord") or ""),
                "homonr": str(row.get("homonr") or ""),
                "id": str(row.get("urspr_lopnr") or ""),
            })

        parsed = parse_heading(str(row.get("ord") or ""))
        explicit = parsed["explicit_homonym"]
        homonr = str(row.get("homonr") or "")
        if explicit is not None:
            explicit_sup_counts[explicit] += 1
            if explicit != homonr:
                sup_mismatch.append({
                    "ord": str(row.get("ord") or ""),
                    "normaliserat_ord": str(row.get("normaliserat_ord") or ""),
                    "homonr": homonr,
                    "explicit_homonym": explicit,
                    "id": str(row.get("urspr_lopnr") or ""),
                })

        if is_plain_reference(row):
            category = classify_reference(row)
            reference_counts[category] += 1
            if len(reference_examples[category]) < 40:
                reference_examples[category].append({
                    "heading": str(row.get("ord") or ""),
                    "target": str(row.get("normaliserat_ord") or ""),
                    "homonr": homonr,
                    "ordkl": str(row.get("ordkl") or ""),
                    "text": str(row.get("text") or ""),
                    "id": str(row.get("urspr_lopnr") or ""),
                })

    summary = {
        "rows": len(rows),
        "ord_stycke_relations": dict(relation_counts.most_common()),
        "rows_with_explicit_superscript_homonym": sum(explicit_sup_counts.values()),
        "explicit_superscript_numbers": dict(sorted(explicit_sup_counts.items(), key=lambda item: int(item[0]))),
        "explicit_superscript_homonr_mismatches": len(sup_mismatch),
        "reference_rows": sum(reference_counts.values()),
        "reference_categories": dict(reference_counts.most_common()),
    }
    details = [{"kind": "superscript_mismatch", **item} for item in sup_mismatch]
    for relation, examples in relation_examples.items():
        details.extend({"kind": f"ord_stycke:{relation}", **item} for item in examples)
    for category, examples in reference_examples.items():
        details.extend({"kind": f"reference:{category}", **item} for item in examples)
    return details, summary


def render(details: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Rå-rader: {summary['rows']}",
        f"Rader med explicit <sup>n</sup> i ord: {summary['rows_with_explicit_superscript_homonym']}",
        f"Explicit <sup>n</sup> som inte stämmer med homonr: {summary['explicit_superscript_homonr_mismatches']}",
        f"Hänvisningsrader ((hv)*): {summary['reference_rows']}",
        "",
        "Relation ord ↔ stycke:",
    ]
    for relation, count in summary["ord_stycke_relations"].items():
        lines.append(f"  {count:6d}  {relation}")
    lines.extend(["", "Explicit homonymnummer i ord:"])
    for number, count in summary["explicit_superscript_numbers"].items():
        lines.append(f"  {count:6d}  {number}")
    lines.extend(["", "Hänvisningstyper:"])
    for category, count in summary["reference_categories"].items():
        lines.append(f"  {count:6d}  {category}")

    mismatches = [item for item in details if item["kind"] == "superscript_mismatch"]
    lines.extend(["", f"<sup>n</sup>/homonr-avvikelser ({len(mismatches)}):"])
    for item in mismatches[:100]:
        lines.append(
            f"  {item['ord']} | normaliserat={item['normaliserat_ord']} | "
            f"homonr={item['homonr']} | sup={item['explicit_homonym']} | id={item['id']}"
        )

    for prefix, heading in (
        ("ord_stycke:", "Exempel där ord och stycke inte är identiska"),
        ("reference:", "Exempel per hänvisningstyp"),
    ):
        lines.extend(["", heading + ":"])
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in details:
            if item["kind"].startswith(prefix):
                grouped[item["kind"].split(":", 1)[1]].append(item)
        for category, examples in sorted(grouped.items()):
            lines.append(f"  [{category}]")
            for item in examples[:20]:
                if prefix == "ord_stycke:":
                    lines.append(
                        f"    ord={item['ord']} | stycke={item['stycke']} | "
                        f"normaliserat={item['normaliserat_ord']} | homonr={item['homonr']} | id={item['id']}"
                    )
                else:
                    lines.append(
                        f"    {item['heading']} -> {item['target']} | homonr={item['homonr']} | "
                        f"ordkl={item['ordkl']} | text={item['text']} | id={item['id']}"
                    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analysera rubrikformat, homonym-superscript och (hv)-hänvisningar i SAOL14-exporten")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    details, summary = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(details, summary), encoding="utf-8")
    args.json.write_text(json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Rå-rader: {summary['rows']}")
    print(f"ord/stycke: {summary['ord_stycke_relations']}")
    print(f"<sup>/homonr-avvikelser: {summary['explicit_superscript_homonr_mismatches']}")
    print(f"Hänvisningar: {summary['reference_categories']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
