from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def reconstruct_source_rows(
    articles: Iterable[dict[str, Any]],
    headings: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct the lexical source rows needed by the noun generator.

    The relations are the canonical interpretation layer.  This function does
    not infer homonyms or alternate headings; it merely joins already
    materialised headings back to their article metadata and restores the
    source-shaped fields consumed by the existing noun paradigm code.
    """

    article_by_id = {str(row.get("article_id") or ""): row for row in articles}
    rows: list[dict[str, Any]] = []

    for heading in headings:
        article_id = str(heading.get("article_id") or "")
        article = article_by_id.get(article_id)
        if article is None:
            raise ValueError(f"Heading references unknown article_id: {article_id!r}")

        # Prefer source-row provenance from headings.  Fall back to the article
        # only for older materialised files that predate those columns.
        source_homonr = str(
            heading.get("source_homonym_number")
            if heading.get("source_homonym_number") is not None
            else ("0" if heading.get("heading_type") == "alternate" else article.get("homonym_number") or "")
        )
        rows.append({
            "normaliserat_ord": str(heading.get("lemma") or article.get("lemma") or ""),
            "homonr": source_homonr,
            "ordkl": str(heading.get("ordkl") or article.get("ordkl") or ""),
            "stycke": str(heading.get("stycke") or heading.get("heading") or ""),
            "urspr_lopnr": str(heading.get("source_id") or article.get("source_id") or ""),
            "subnr": str(heading.get("subnr") or article.get("subnr") or ""),
            "text": str(heading.get("notation") or article.get("notation") or ""),
            "source": str(heading.get("source") or article.get("source") or ""),
            "upos": str(heading.get("upos") or article.get("upos") or ""),
            "ord": str(heading.get("heading") or ""),
            "_source_row_index": int(heading.get("source_row_index") or 0),
            "_article_id": article_id,
        })

    rows.sort(key=lambda row: row["_source_row_index"])
    for row in rows:
        row.pop("_source_row_index", None)
        row.pop("_article_id", None)
    return rows


def relational_integrity_summary(
    articles: Iterable[dict[str, Any]],
    headings: Iterable[dict[str, Any]],
) -> dict[str, int]:
    article_rows = list(articles)
    heading_rows = list(headings)
    article_ids = {str(row.get("article_id") or "") for row in article_rows}
    dangling = sum(str(row.get("article_id") or "") not in article_ids for row in heading_rows)
    by_article: dict[str, int] = defaultdict(int)
    for row in heading_rows:
        by_article[str(row.get("article_id") or "")] += 1
    return {
        "articles": len(article_rows),
        "headings": len(heading_rows),
        "dangling_headings": dangling,
        "articles_without_headings": sum(article_id not in by_article for article_id in article_ids),
    }
