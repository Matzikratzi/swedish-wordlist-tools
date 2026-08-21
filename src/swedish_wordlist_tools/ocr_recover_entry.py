from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .ocr_match_jsonl import load_entry
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import group_articles, read_words
from .ocr_recover_tail import recover_tail


MIN_HEADWORD_SCORE = 0.70
MIN_KNOWN_TEXT_SCORE = 0.55
# If the known JSONL text matches strongly, allow a damaged OCR headword. This
# is the important abc-stridsmedel -> abe-stridsimedel case: JSONL supplies the
# identity; OCR only has to locate the printed article and recover its suffix.
ANCHORED_MIN_HEADWORD_SCORE = 0.30
ANCHORED_MIN_KNOWN_TEXT_SCORE = 0.64


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def _image_size(image: Path) -> tuple[int, int]:
    out = subprocess.check_output(["identify", "-format", "%w %h", str(image)], text=True)
    w, h = out.strip().split()
    return int(w), int(h)


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)


def _crop_columns(image: Path, workdir: Path) -> list[Path]:
    width, height = _image_size(image)
    third = width / 3
    overlap = max(6, round(width * 0.015))
    columns: list[Path] = []
    for i in range(3):
        left = max(0, round(i * third) - overlap)
        right = min(width, round((i + 1) * third) + overlap)
        crop = workdir / f"column-{i + 1}.png"
        _run("convert", str(image), "-crop", f"{right-left}x{height}+{left}+0", "+repage", str(crop))
        columns.append(crop)
    return columns


def _ocr_tsv(image: Path, dest: Path) -> None:
    base = dest.with_suffix("")
    _run("tesseract", str(image), str(base), "-l", "swe", "--psm", "6", "tsv")
    generated = base.with_suffix(".tsv")
    if generated != dest:
        generated.replace(dest)


def _soft(text: str) -> str:
    text = normalize_text_for_match(text)
    return " ".join(part.lstrip("+~-–—") for part in text.split())


def _headword_score(entry: dict[str, object], article_text: str) -> float:
    from difflib import SequenceMatcher

    def compact(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return "".join(ch for ch in normalize_text_for_match(value) if ch.isalnum())

    targets = [compact(entry.get(k)) for k in ("normaliserat_ord", "stycke", "ord")]
    targets = [x for x in targets if x]
    article = compact(article_text)
    best = 0.0
    for target in targets:
        # Compare against the printed prefix only. Permit a little extra OCR
        # material because punctuation/style boundaries often get fused.
        for extra in range(0, 4):
            prefix = article[: len(target) + extra]
            if prefix:
                best = max(best, SequenceMatcher(None, target, prefix).ratio())
    return best


def _known_text_score(entry: dict[str, object], article_text: str) -> float:
    from difflib import SequenceMatcher

    known = _soft(str(entry.get("text") or ""))
    haystack = _soft(article_text)
    if not known:
        return 0.0
    if known in haystack:
        return 1.0
    target = known.split()
    words = haystack.split()
    best = 0.0
    for width in range(max(1, len(target) - 1), len(target) + 2):
        for start in range(max(0, len(words) - width + 1)):
            best = max(best, SequenceMatcher(None, known, " ".join(words[start:start + width])).ratio())
    return best


def _candidate(entry: dict[str, object], article, column: int) -> dict[str, object]:
    article_text = " ".join(word.text for line in article.lines for word in line.words)
    hs = _headword_score(entry, article_text)
    ks = _known_text_score(entry, article_text)
    anchored = hs >= ANCHORED_MIN_HEADWORD_SCORE and ks >= ANCHORED_MIN_KNOWN_TEXT_SCORE
    conventional = hs >= MIN_HEADWORD_SCORE and ks >= MIN_KNOWN_TEXT_SCORE
    recovery = recover_tail(entry, article, 0.8 * hs + 0.2 * ks, hs)
    data = recovery.__dict__.copy()
    data.update({
        "column": column,
        "headword_score": round(hs, 4),
        "known_text_score": round(ks, 4),
        "acceptable": conventional or anchored,
        "match_mode": "jsonl-anchor" if anchored and not conventional else ("normal" if conventional else None),
    })
    return data


def _selection_key(result: dict[str, object]) -> tuple[float, float, float]:
    # Once the known 50-char field anchors us to an article, it is stronger
    # evidence than exact OCR of a styled headword.
    return (
        float(result.get("known_text_score", 0.0)),
        float(result.get("headword_score", 0.0)),
        float(result.get("article_score", 0.0)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover one truncated SAOL14 entry from its facsimile page.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--subnr", type=int, required=True)
    parser.add_argument("--keep-workdir", type=Path)
    args = parser.parse_args()

    entry = load_entry(args.jsonl, args.subnr)
    source = entry.get("source")
    if not isinstance(source, str) or not source.startswith("http"):
        raise SystemExit("entry has no usable source URL")

    owned_tmp = None
    if args.keep_workdir:
        workdir = args.keep_workdir
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        owned_tmp = tempfile.TemporaryDirectory(prefix="saol14-ocr-")
        workdir = Path(owned_tmp.name)

    page = workdir / Path(source).name
    if not page.exists():
        _download(source, page)
    columns = _crop_columns(page, workdir)

    results: list[dict[str, object]] = []
    for idx, column in enumerate(columns, 1):
        tsv = workdir / f"column-{idx}.tsv"
        _ocr_tsv(column, tsv)
        with tsv.open("r", encoding="utf-8", newline="") as stream:
            articles = group_articles(read_words(stream))
        results.extend(_candidate(entry, article, idx) for article in articles)

    acceptable = [r for r in results if r.get("acceptable") is True]
    best = max(acceptable, key=_selection_key, default=None)
    output = {
        "entry": {k: entry.get(k) for k in ("normaliserat_ord", "subnr", "sidnr1", "text", "source")},
        "best": best,
        "status": "matched" if best is not None else "review-no-confident-jsonl-anchor",
        "thresholds": {
            "min_headword_score": MIN_HEADWORD_SCORE,
            "min_known_text_score": MIN_KNOWN_TEXT_SCORE,
            "anchored_min_headword_score": ANCHORED_MIN_HEADWORD_SCORE,
            "anchored_min_known_text_score": ANCHORED_MIN_KNOWN_TEXT_SCORE,
        },
        "candidate_count": len(results),
        "acceptable_count": len(acceptable),
        "top_candidates": sorted(results, key=_selection_key, reverse=True)[:5],
    }
    json.dump(output, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
