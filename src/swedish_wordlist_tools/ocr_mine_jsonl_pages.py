from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def _source_for_page(jsonl: Path, page: int) -> str | None:
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("sidnr1") == page and isinstance(entry.get("source"), str):
                return entry["source"]
    return None


def _crop_columns(image: Path, workdir: Path) -> list[Path]:
    identify = subprocess.check_output(["identify", "-format", "%w %h", str(image)], text=True).strip()
    width, height = map(int, identify.split())
    third = width / 3
    overlap = max(6, round(width * 0.015))
    out: list[Path] = []
    for i in range(3):
        left = max(0, round(i * third) - overlap)
        right = min(width, round((i + 1) * third) + overlap)
        crop = workdir / f"page-column-{i+1}.png"
        subprocess.run(
            ["convert", str(image), "-crop", f"{right-left}x{height}+{left}+0", "+repage", str(crop)],
            check=True,
        )
        out.append(crop)
    return out


def _ocr_tsv(image: Path, tsv: Path) -> None:
    base = tsv.with_suffix("")
    subprocess.run(["tesseract", str(image), str(base), "-l", "swe", "--psm", "6", "tsv"], check=True)
    generated = base.with_suffix(".tsv")
    if generated != tsv:
        generated.replace(tsv)


def _inventory(style_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not style_dir.exists():
        return counts
    for path in style_dir.glob("*.png"):
        ch = path.name.split("-", 1)[0]
        counts[ch] = counts.get(ch, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine SAOL italic glyph templates across several facsimile pages.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--pages", required=True, help="Page list/ranges, e.g. 1-8,10,12")
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--keep-workdir", type=Path)
    parser.add_argument("--limit-per-char", type=int, default=20)
    args = parser.parse_args()

    pages: list[int] = []
    for part in args.pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = map(int, part.split("-", 1))
            pages.extend(range(a, b + 1))
        else:
            pages.append(int(part))
    pages = sorted(set(pages))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    before_inventory = _inventory(args.out_dir / "italic")

    owned = None
    if args.keep_workdir:
        root = args.keep_workdir
        root.mkdir(parents=True, exist_ok=True)
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-glyph-pages-")
        root = Path(owned.name)

    run_counts: dict[str, int] = {}
    page_results: list[dict[str, object]] = []

    for page in pages:
        source = _source_for_page(args.jsonl, page)
        if not source:
            page_results.append({"page": page, "error": "no source"})
            continue
        page_dir = root / f"page-{page:05d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        image = page_dir / Path(source).name
        if not image.exists():
            _download(source, image)
        columns = _crop_columns(image, page_dir)
        column_results: list[dict[str, object]] = []
        for idx, column in enumerate(columns, 1):
            tsv = page_dir / f"column-{idx}.tsv"
            _ocr_tsv(column, tsv)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "swedish_wordlist_tools.ocr_mine_jsonl_templates",
                    str(args.jsonl),
                    str(column),
                    str(tsv),
                    "--page",
                    str(page),
                    "--chars",
                    args.chars,
                    "--out-dir",
                    str(args.out_dir),
                    "--limit-per-char",
                    str(args.limit_per_char),
                ],
                text=True,
                capture_output=True,
            )
            if proc.returncode != 0:
                column_results.append({"column": idx, "error": proc.stderr.strip() or proc.stdout.strip()})
                continue
            data = json.loads(proc.stdout)
            counts = data.get("counts", {})
            if isinstance(counts, dict):
                for ch, n in counts.items():
                    run_counts[str(ch)] = run_counts.get(str(ch), 0) + int(n)
            column_results.append({"column": idx, "matched_entries": data.get("matched_entries"), "counts": counts})
        page_results.append({"page": page, "columns": column_results})

    after_inventory = _inventory(args.out_dir / "italic")
    result = {
        "pages": pages,
        "run_counts": dict(sorted(run_counts.items())),
        "library_before": before_inventory,
        "library_after": after_inventory,
        "page_results": page_results,
    }
    (args.out_dir / "manifest-pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
