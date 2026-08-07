from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_article_headings import materialize_heading_model

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
        for item in article["headings"]:
            headings.append({
                "article_id": aid,
                "heading": item["heading"],
                "heading_type": item["type"],
                "lemma": article["normalised_word"],
                "homonym_number": article["homonym_number"],
                "source_id": article["source_id"],
            })

    for ref in model["references"]:
        references.append({
            "reference_id": f"{ref['source_id']}:{ref['subnr']}:{ref['source_homonr']}:{ref['heading']}",
            "source_id": ref["source_id"],
            "subnr": ref["subnr"],
            "source_homonym_number": ref["source_homonr"],
            "source_heading": ref["heading"],
            "target_lemma": ref["target_normalised_word"],
            "reference_type": reference_type(ref),
            "ordkl": ref["ordkl"],
            "notation": ref["text"],
            "source": ref["source"],
        })

    article_ids = {row["article_id"] for row in articles}
    dangling_headings = [row for row in headings if row["article_id"] not in article_ids]
    source_rows_accounted = sum(row["source_row_count"] for row in articles) + len(references)
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
        f"Rubriker: {summary['headings']} (primära {summary['primary_headings']}, alternativa {summary['alternate_headings']})",
        f"Hänvisningar: {summary['references']} {summary['reference_types']}",
        f"Unika article_id: {summary['unique_article_ids']}",
        f"Rubriker utan artikel: {summary['dangling_headings']}",
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
