from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_ALIGNMENT = Path("reports/saol14-noun-variant-saldo-alignment.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-missing-saldo-variant-lemmas.txt")
DEFAULT_JSONL = Path("reports/saol14-noun-missing-saldo-variant-lemmas.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-missing-saldo-variant-lemmas-summary.json")

_SEPARATOR_RE = re.compile(r"[\s\-_]+")


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _without_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _compact(value: str) -> str:
    return _SEPARATOR_RE.sub("", _fold(value))


def _edit_distance(a: str, b: str, *, limit: int = 3) -> int:
    a = _fold(a)
    b = _fold(b)
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            ))
            row_min = min(row_min, current[-1])
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def relation(article_lemma: str, variant_lemma: str) -> str:
    if variant_lemma == article_lemma:
        return "same_as_article_lemma"
    if _fold(variant_lemma) == _fold(article_lemma):
        return "case_only"
    if _compact(variant_lemma) == _compact(article_lemma):
        return "spacing_or_hyphen_only"
    if _without_diacritics(_fold(variant_lemma)) == _without_diacritics(_fold(article_lemma)):
        return "diacritic_only"
    distance = _edit_distance(article_lemma, variant_lemma)
    if distance == 1:
        return "edit_distance_1"
    if distance == 2:
        return "edit_distance_2"
    return "other_spelling"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def classify(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = list(rows)
    by_article: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source:
        key = (str(row.get("record_id") or ""), str(row.get("homonym_number") or ""))
        by_article[key].append(row)

    output: list[dict[str, Any]] = []
    for key, article_rows in by_article.items():
        any_found = any(str(row.get("status") or "") != "missing" for row in article_rows)
        all_missing = all(str(row.get("status") or "") == "missing" for row in article_rows)
        for row in article_rows:
            if str(row.get("status") or "") != "missing":
                continue
            article_lemma = str(row.get("article_lemma") or "")
            variant_lemma = str(row.get("variant_lemma") or "")
            output.append({
                "record_id": key[0],
                "homonym_number": key[1],
                "article_lemma": article_lemma,
                "variant_lemma": variant_lemma,
                "variant_mode": str(row.get("variant_mode") or ""),
                "relation_to_article_lemma": relation(article_lemma, variant_lemma),
                "article_has_other_saldo_match": any_found,
                "article_all_variants_missing": all_missing,
                "saol_forms": list(row.get("saol_forms") or ()),
            })

    output.sort(key=lambda row: (
        not bool(row["article_all_variants_missing"]),
        str(row["relation_to_article_lemma"]),
        str(row["article_lemma"]).casefold(),
        str(row["variant_lemma"]).casefold(),
    ))
    relation_counts = Counter(str(row["relation_to_article_lemma"]) for row in output)
    mode_counts = Counter(str(row["variant_mode"]) for row in output)
    article_keys = {(str(row["record_id"]), str(row["homonym_number"])) for row in output}
    all_missing_articles = {
        (str(row["record_id"]), str(row["homonym_number"]))
        for row in output
        if row["article_all_variants_missing"]
    }
    partial_articles = article_keys - all_missing_articles
    summary = {
        "missing_variant_paradigms": len(output),
        "affected_articles": len(article_keys),
        "articles_all_variants_missing": len(all_missing_articles),
        "articles_with_some_saldo_match": len(partial_articles),
        "relation_counts": dict(sorted(relation_counts.items())),
        "variant_mode_counts": dict(sorted(mode_counts.items())),
    }
    return output, summary


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Saknade variantparadigm: {summary['missing_variant_paradigms']}",
        f"Berörda artiklar: {summary['affected_articles']}",
        f"Artiklar där alla varianter saknas i SALDO: {summary['articles_all_variants_missing']}",
        f"Artiklar där minst en annan variant finns i SALDO: {summary['articles_with_some_saldo_match']}",
        f"Relationer till huvudlemma: {summary['relation_counts']}",
        f"Variantlägen: {summary['variant_mode_counts']}",
        "",
        "Saknade varianter grupperade efter relation:",
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["relation_to_article_lemma"])].append(row)
    for relation_name, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f"\n{relation_name}: {len(members)}")
        for row in members[:80]:
            scope = "hela artikeln saknas" if row["article_all_variants_missing"] else "annan variant finns i SALDO"
            lines.append(
                f"  {row['article_lemma']} -> {row['variant_lemma']} "
                f"[{row['variant_mode']}; {scope}; record_id={row['record_id']}; homonr={row['homonym_number']}]"
            )
        if len(members) > 80:
            lines.append(f"  ... ytterligare {len(members) - 80}")
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify SAOL noun variant lemmas missing from the materialized SALDO artifact")
    parser.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows, summary = classify(read_jsonl(args.alignment))
    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows, summary), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saknade variantparadigm: {summary['missing_variant_paradigms']}")
    print(f"Berörda artiklar: {summary['affected_articles']}")
    print(f"Alla varianter saknas: {summary['articles_all_variants_missing']}")
    print(f"Någon variant finns: {summary['articles_with_some_saldo_match']}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
