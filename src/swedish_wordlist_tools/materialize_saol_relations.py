from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_article_headings import id_key, is_plain_reference, materialize_heading_model

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_ARTICLES = Path("reports/saol14-articles.jsonl")
DEFAULT_HEADINGS = Path("reports/saol14-headings.jsonl")
DEFAULT_REFERENCES = Path("reports/saol14-references.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-relational-model-summary.json")
DEFAULT_TEXT = Path("reports/saol14-relational-model-audit.txt")


def article_id(source_id: str, subnr: str, homonym_number: str) -> str:
    return f"{source_id}:{subnr}:{homonym_number}"


def reference_type(row: dict[str, Any]) -> str:
    ordkl = str(row.get("ordkl") or "").casefold()
    text = str(row.get("text") or "").casefold()
    if "komp." in ordkl or "komp." in text or "superl." in ordkl or "superl." in text:
        return "inflection_reference"
    if "<i>" in ordkl:
        return "morphology_annotated_reference"
    return "plain_reference"


def materialize(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows = list(records)
    model = materialize_heading_model(rows)
    articles: list[dict[str, Any]] = []
    headings: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []

    # Keep the relation model article-based, but preserve every lexical source
    # row in the heading relation.  This makes the materialisation lossless for
    # downstream generators: ord/stycke, raw homonr and duplicate source rows
    # can be reconstructed without reopening the original JSONL.
    grouped: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for source_row_index, row in enumerate(rows):
        grouped[id_key(row)].append((source_row_index, row))

    for article in model["articles"]:
        aid = article_id(article["source_id"], article["subnr"], article["homonym_number"])
        articles.append({
            "article_id": aid,
            "source_id": article["source_id"],
            "subnr": article["subnr"],
            "lemma": article["normalised_word"],
            "homonym_number": article["homonym_number"],
            "upos": article["upos"],
            "ordkl": article["ordkl"],
            "notation": article["text"],
            "source": article["source"],
            "source_row_count": article["source_row_count"],
        })

    article_ids = {row["article_id"] for row in articles}

    for key, indexed_peers in grouped.items():
        lexical = [(idx, row) for idx, row in indexed_peers if not is_plain_reference(row)]
        nonzero_homonyms = sorted({
            str(row.get("homonr") or "")
            for _idx, row in lexical
            if str(row.get("homonr") or "") not in {"", "0"}
        })
        zero_anchor = nonzero_homonyms[0] if len(nonzero_homonyms) == 1 else None

        for source_row_index, row in indexed_peers:
            if is_plain_reference(row):
                references.append({
                    "reference_id": f"{key[0]}:{key[1]}:{str(row.get('homonr') or '')}:{str(row.get('ord') or '')}",
                    "source_id": key[0],
                    "subnr": key[1],
                    "source_homonym_number": str(row.get("homonr") or ""),
                    "source_heading": str(row.get("ord") or row.get("stycke") or row.get("normaliserat_ord") or ""),
                    "target_lemma": str(row.get("normaliserat_ord") or ""),
                    "reference_type": reference_type(row),
                    "ordkl": str(row.get("ordkl") or ""),
                    "notation": str(row.get("text") or ""),
                    "source": str(row.get("source") or ""),
                    "source_row_index": source_row_index,
                })
                continue

            raw_homonr = str(row.get("homonr") or "")
            anchor_homonr = raw_homonr if raw_homonr not in {"", "0"} else zero_anchor
            aid = article_id(key[0], key[1], anchor_homonr) if anchor_homonr else ""
            headings.append({
                "article_id": aid,
                "heading": str(row.get("ord") or row.get("stycke") or row.get("normaliserat_ord") or ""),
                "heading_type": "primary" if raw_homonr not in {"", "0"} else "alternate",
                "lemma": str(row.get("normaliserat_ord") or ""),
                "homonym_number": str(anchor_homonr or ""),
                "source_homonym_number": raw_homonr,
                "source_id": key[0],
                "subnr": key[1],
                "stycke": str(row.get("stycke") or ""),
                "upos": str(row.get("upos") or ""),
                "ordkl": str(row.get("ordkl") or ""),
                "notation": str(row.get("text") or ""),
                "source": str(row.get("source") or ""),
                "source_row_index": source_row_index,
            })

    headings.sort(key=lambda row: int(row["source_row_index"]))
    references.sort(key=lambda row: int(row["source_row_index"]))
    dangling_headings = [row for row in headings if not row["article_id"] or row["article_id"] not in article_ids]
    source_rows_accounted = len(headings) + len(references)
    summary = {
        "raw_rows": len(rows),
        "articles": len(articles),
        "headings": len(headings),
        "references": len(references),
        "primary_headings": sum(row["heading_type"] == "primary" for row in headings),
        "alternate_headings": sum(row["heading_type"] == "alternate" for row in headings),
        "reference_types": dict(Counter(row["reference_type"] for row in references)),
        "unique_article_ids": len(article_ids),
        "dangling_headings": len(dangling_headings),
        "unresolved": len(model["unresolved"]),
        "source_rows_accounted": source_rows_accounted,
        "raw_rows_minus_accounted": len(rows) - source_rows_accounted,
    }
    return articles, headings, references, summary


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def render(summary: dict[str, Any]) -> str:
    return "\n".join([
        f"Rå-rader: {summary['raw_rows']}",
        f"Artiklar/homonymer: {summary['articles']}",
        f"Rubrikrader: {summary['headings']} (primära {summary['primary_headings']}, alternativa {summary['alternate_headings']})",
        f"Hänvisningar: {summary['references']} {summary['reference_types']}",
        f"Unika article_id: {summary['unique_article_ids']}",
        f"Rubrikrader utan artikel: {summary['dangling_headings']}",
        f"Olösta strukturer: {summary['unresolved']}",
        f"Källrader redovisade: {summary['source_rows_accounted']}",
        f"Rå-rader minus redovisade: {summary['raw_rows_minus_accounted']}",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialisera SAOL14 som articles/headings/references")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    args = parser.parse_args()
    articles, headings, references, summary = materialize(read_jsonl(args.saol))
    write_jsonl(DEFAULT_ARTICLES, articles)
    write_jsonl(DEFAULT_HEADINGS, headings)
    write_jsonl(DEFAULT_REFERENCES, references)
    DEFAULT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DEFAULT_TEXT.write_text(render(summary), encoding="utf-8")
    print(render(summary), end="")
    print(f"Articles: {DEFAULT_ARTICLES}")
    print(f"Headings: {DEFAULT_HEADINGS}")
    print(f"References: {DEFAULT_REFERENCES}")


if __name__ == "__main__":
    main()
