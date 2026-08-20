from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .ocr_match_jsonl import load_entry


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
    # SAOL facsimile pages are three-column pages. Give each crop a little
    # horizontal overlap so headwords near a gutter are not clipped.
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
    _download(source, page)
    columns = _crop_columns(page, workdir)

    results = []
    entry_json = json.dumps(entry, ensure_ascii=False)
    for idx, column in enumerate(columns, 1):
        tsv = workdir / f"column-{idx}.tsv"
        _ocr_tsv(column, tsv)
        proc = subprocess.run(
            [
                __import__("sys").executable,
                "-m",
                "swedish_wordlist_tools.ocr_recover_tail",
                str(tsv),
                "--entry-json",
                entry_json,
            ],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            results.append({"column": idx, "error": proc.stderr.strip() or proc.stdout.strip()})
            continue
        data = json.loads(proc.stdout)
        data["column"] = idx
        results.append(data)

    successful = [r for r in results if "article_score" in r]
    best = max(successful, key=lambda r: float(r.get("article_score", 0.0)), default=None)
    output = {
        "entry": {
            "normaliserat_ord": entry.get("normaliserat_ord"),
            "subnr": entry.get("subnr"),
            "sidnr1": entry.get("sidnr1"),
            "text": entry.get("text"),
            "source": source,
        },
        "best": best,
        "columns": results,
    }
    json.dump(output, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
