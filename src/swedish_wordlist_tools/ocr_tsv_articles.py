from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, TextIO


@dataclass(frozen=True)
class OcrWord:
    block: int
    paragraph: int
    line: int
    word: int
    left: int
    top: int
    width: int
    height: int
    confidence: float
    text: str


@dataclass(frozen=True)
class OcrLine:
    block: int
    paragraph: int
    line: int
    words: tuple[OcrWord, ...]


@dataclass(frozen=True)
class OcrArticle:
    block: int
    paragraph: int
    lines: tuple[OcrLine, ...]


def _int(row: dict[str, str], key: str) -> int:
    return int(row[key])


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def read_words(stream: TextIO) -> list[OcrWord]:
    """Read word-level rows from Tesseract TSV output.

    Tesseract emits rows for page/block/paragraph/line levels too.  Only level 5
    rows contain individual OCR words, so the structural rows are ignored here.
    Empty word rows are ignored as well.
    """

    reader = csv.DictReader(stream, delimiter="\t")
    words: list[OcrWord] = []
    for row in reader:
        if row.get("level") != "5":
            continue
        text = row.get("text", "")
        if not text:
            continue
        words.append(
            OcrWord(
                block=_int(row, "block_num"),
                paragraph=_int(row, "par_num"),
                line=_int(row, "line_num"),
                word=_int(row, "word_num"),
                left=_int(row, "left"),
                top=_int(row, "top"),
                width=_int(row, "width"),
                height=_int(row, "height"),
                confidence=_float(row, "conf"),
                text=text,
            )
        )
    return words


def group_articles(words: Iterable[OcrWord]) -> list[OcrArticle]:
    """Group OCR words into Tesseract paragraphs and lines.

    For the SAOL14 facsimile tests so far, a Tesseract paragraph maps neatly to
    one dictionary article after cropping to a single column.  This function
    deliberately preserves that raw grouping and does not yet attempt any SAOL
    normalisation or OCR correction.
    """

    paragraphs: dict[tuple[int, int], dict[int, list[OcrWord]]] = {}
    for word in words:
        key = (word.block, word.paragraph)
        paragraphs.setdefault(key, {}).setdefault(word.line, []).append(word)

    articles: list[OcrArticle] = []
    for (block, paragraph), lines_by_num in sorted(paragraphs.items()):
        lines: list[OcrLine] = []
        for line_num, line_words in sorted(lines_by_num.items()):
            ordered_words = tuple(sorted(line_words, key=lambda item: (item.left, item.word)))
            lines.append(
                OcrLine(
                    block=block,
                    paragraph=paragraph,
                    line=line_num,
                    words=ordered_words,
                )
            )
        articles.append(
            OcrArticle(
                block=block,
                paragraph=paragraph,
                lines=tuple(lines),
            )
        )
    return articles


def article_to_json(article: OcrArticle) -> dict[str, object]:
    return {
        "block": article.block,
        "paragraph": article.paragraph,
        "lines": [
            {
                "line": line.line,
                "text": " ".join(word.text for word in line.words),
                "words": [asdict(word) for word in line.words],
            }
            for line in article.lines
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Group word-level Tesseract TSV into paragraph/article JSON."
    )
    parser.add_argument("tsv", type=Path, help="Tesseract TSV file")
    parser.add_argument(
        "--paragraph",
        type=int,
        help="Only emit this Tesseract paragraph number",
    )
    args = parser.parse_args()

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        articles = group_articles(read_words(stream))

    if args.paragraph is not None:
        articles = [article for article in articles if article.paragraph == args.paragraph]

    json.dump(
        [article_to_json(article) for article in articles],
        fp=__import__("sys").stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
