from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .saol_article_headings import materialize_heading_model

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-article-heading-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-article-heading-analysis.json")


def analyze(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    model = materialize_heading_model(rows)
    articles = model["articles"]
    references = model["references"]
    unresolved = model["unresolved"]

    articles_by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_word[article["normalised_word"]].append(article)

    homonym_count_distribution = Counter(len(items) for items in articles_by_word.values())
    alternate_anchor_counts = Counter(article["homonym_number"] for article in articles if article["alternate_headings"])
    reference_homonr_counts = Counter(ref["source_homonr"] for ref in references)
    unresolved_counts = Counter(item["kind"] for item in unresolved)

    multi_homonym_with_alternates = []
    for word, items in sorted(articles_by_word.items(), key=lambda item: item[0].casefold()):
        homonyms = {item["homonym_number"] for item in items}
        with_alternates = [item for item in items if item["alternate_headings"]]
        if len(homonyms) > 1 and with_alternates:
            multi_homonym_with_alternates.append({
                "normalised_word": word,
                "homonym_numbers": sorted(homonyms),
                "articles": [
                    {
                        "source_id": item["source_id"],
                        "homonym_number": item["homonym_number"],
                        "primary_headings": item["primary_headings"],
                        "alternate_headings": item["alternate_headings"],
                    }
                    for item in items
                ],
            })

    summary = {
        "article_homonyms": len(articles),
        "normalised_words_with_articles": len(articles_by_word),
        "reference_entries": len(references),
        "articles_with_alternate_headings": sum(1 for article in articles if article["alternate_headings"]),
        "alternate_heading_count": sum(len(article["alternate_headings"]) for article in articles),
        "homonym_count_distribution": dict(sorted(homonym_count_distribution.items())),
        "alternate_heading_anchor_homonr": dict(sorted(alternate_anchor_counts.items())),
        "reference_homonr_counts": dict(sorted(reference_homonr_counts.items())),
        "multi_homonym_words_with_alternate_headings": len(multi_homonym_with_alternates),
        "unresolved_counts": dict(sorted(unresolved_counts.items())),
    }
    details = {
        "summary": summary,
        "multi_homonym_with_alternates": multi_homonym_with_alternates,
        "unresolved": unresolved,
        "references": references,
    }
    return summary, details


def render(summary: dict[str, Any], details: dict[str, Any]) -> str:
    lines = [
        f"Materialiserade artikelhomonymer: {summary['article_homonyms']}",
        f"Normaliserade ord med artiklar: {summary['normalised_words_with_articles']}",
        f"Hänvisningsposter ((hv)): {summary['reference_entries']}",
        f"Artiklar med alternativa rubriker: {summary['articles_with_alternate_headings']}",
        f"Alternativa rubriker totalt: {summary['alternate_heading_count']}",
        f"Homonymer per normaliserat ord: {summary['homonym_count_distribution']}",
        f"Alternativ rubrik knuten till homonr: {summary['alternate_heading_anchor_homonr']}",
        f"Hänvisningsposternas homonr: {summary['reference_homonr_counts']}",
        f"Ord med flera riktiga homonymer där minst en har alternativ rubrik: {summary['multi_homonym_words_with_alternate_headings']}",
        f"Olösta strukturer: {summary['unresolved_counts']}",
        "",
        "Flera homonymer + alternativa rubriker:",
    ]
    for item in details["multi_homonym_with_alternates"][:100]:
        lines.append(f"  {item['normalised_word']} | homonymer={','.join(item['homonym_numbers'])}")
        for article in item["articles"]:
            lines.append(
                f"    homonr={article['homonym_number']} id={article['source_id']} | "
                f"primär={article['primary_headings']} | alternativ={article['alternate_headings']}"
            )
    lines.extend(["", "Olösta strukturer:"])
    for item in details["unresolved"][:100]:
        lines.append(f"  {item}")
    lines.extend(["", "Exempel på hänvisningsposter ((hv)):"])
    for ref in details["references"][:100]:
        lines.append(
            f"  {ref['heading']} -> {ref['target_normalised_word']} | "
            f"homonr={ref['source_homonr']} | id={ref['source_id']}"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analysera SAOL:s riktiga homonymer, artikelrubriker och hänvisningsposter")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    rows = list(read_jsonl(args.saol))
    summary, details = analyze(rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary, details), encoding="utf-8")
    args.json.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Artikelhomonymer: {summary['article_homonyms']}")
    print(f"Hänvisningsposter: {summary['reference_entries']}")
    print(f"Artiklar med alternativa rubriker: {summary['articles_with_alternate_headings']}")
    print(f"Flera homonymer + alternativ rubrik: {summary['multi_homonym_words_with_alternate_headings']}")
    print(f"Olösta: {summary['unresolved_counts']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
