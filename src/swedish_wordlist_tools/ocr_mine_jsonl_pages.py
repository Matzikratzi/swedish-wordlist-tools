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


def _crop_columns(image: Path, workdir: Path) -> list[tuple[Path, int]]:
    identify = subprocess.check_output(["identify", "-format", "%w %h", str(image)], text=True).strip()
    width, height = map(int, identify.split())
    third = width / 3
    overlap = max(6, round(width * 0.015))
    out: list[tuple[Path, int]] = []
    for i in range(3):
        left = max(0, round(i * third) - overlap)
        right = min(width, round((i + 1) * third) + overlap)
        crop = workdir / f"page-column-{i+1}.png"
        if not crop.exists():
            subprocess.run(["convert", str(image), "-crop", f"{right-left}x{height}+{left}+0", "+repage", str(crop)], check=True)
        out.append((crop, left))
    return out


def _ocr_tsv(image: Path, tsv: Path) -> None:
    if tsv.exists() and tsv.stat().st_size > 0:
        return
    base = tsv.with_suffix("")
    subprocess.run(["tesseract", str(image), str(base), "-l", "swe", "--psm", "6", "tsv"], check=True)
    generated = base.with_suffix(".tsv")
    if generated != tsv:
        generated.replace(tsv)


def _inventory(style_dir: Path) -> dict[str, int]:
    counts = {}
    if style_dir.exists():
        for path in style_dir.glob("*.png"):
            ch = path.name.split("-", 1)[0]
            counts[ch] = counts.get(ch, 0) + 1
    return dict(sorted(counts.items()))


def _parse_pages(spec: str) -> list[int]:
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = map(int, part.split("-", 1))
            pages.extend(range(a, b + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine separate SAOL glyph template libraries by style.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--styles", default="italic,bold,roman", help="Comma-separated: italic,bold,roman")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--keep-workdir", type=Path)
    parser.add_argument("--limit-per-char", type=int, default=20)
    args = parser.parse_args()

    pages = _parse_pages(args.pages)
    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    bad = [s for s in styles if s not in {"italic", "bold", "roman"}]
    if bad:
        parser.error(f"unknown styles: {','.join(bad)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    before = {style: _inventory(args.out_dir / style) for style in styles}

    owned = None
    if args.keep_workdir:
        root = args.keep_workdir
        root.mkdir(parents=True, exist_ok=True)
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-glyph-pages-")
        root = Path(owned.name)

    run_counts = {style: {} for style in styles}
    page_results = []
    template_sources: dict[str, dict[str, object]] = {}
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
        column_results = []
        for idx, (column, column_left) in enumerate(columns, 1):
            tsv = page_dir / f"column-{idx}.tsv"
            _ocr_tsv(column, tsv)
            style_results = {}
            for style in styles:
                cmd = [sys.executable, "-m", "swedish_wordlist_tools.ocr_mine_jsonl_templates", str(args.jsonl), str(column), str(tsv), "--page", str(page), "--chars", args.chars, "--out-dir", str(args.out_dir), "--limit-per-char", str(args.limit_per_char), "--style", style]
                if style == "italic":
                    cmd.append("--allow-interior")
                proc = subprocess.run(cmd, text=True, capture_output=True)
                if proc.returncode != 0:
                    style_results[style] = {"error": proc.stderr.strip() or proc.stdout.strip()}
                    continue
                data = json.loads(proc.stdout)
                counts = data.get("counts", {})
                for ch, n in counts.items():
                    d = run_counts[style]
                    d[str(ch)] = d.get(str(ch), 0) + int(n)
                templates = data.get("templates", [])
                if isinstance(templates, list):
                    for item in templates:
                        if not isinstance(item, dict):
                            continue
                        output = str(item.get("output") or "")
                        if not output:
                            continue
                        bbox = item.get("bbox")
                        page_bbox = None
                        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                            page_bbox = [int(bbox[0]) + column_left, int(bbox[1]), int(bbox[2]), int(bbox[3])]
                        template_sources[output] = {
                            "page": page,
                            "column": idx,
                            "column_left": column_left,
                            "bbox": bbox,
                            "page_bbox": page_bbox,
                            "source": source,
                            "page_image": str(image),
                            "column_image": str(column),
                            "subnr": item.get("subnr"),
                            "source_word": item.get("source_word"),
                            "expected_word": item.get("expected_word"),
                            "position_kind": item.get("position_kind"),
                            "style": style,
                            "character": item.get("character"),
                        }
                style_results[style] = {
                    "matched_entries": data.get("matched_entries"),
                    "exact_word_matches": data.get("exact_word_matches"),
                    "counts": counts,
                    "rejected_fuzzy_words": data.get("rejected_fuzzy_words"),
                    "rejected_split": data.get("rejected_split"),
                    "rejected_boundary": data.get("rejected_boundary"),
                    "rejected_charbox_count": data.get("rejected_charbox_count"),
                    "rejected_charbox_labels": data.get("rejected_charbox_labels"),
                    "rejected_geometry": data.get("rejected_geometry"),
                    "fuzzy_examples": data.get("fuzzy_examples", []),
                }
            column_results.append({"column": idx, "column_left": column_left, "styles": style_results})
        page_results.append({"page": page, "source": source, "columns": column_results})

    after = {style: _inventory(args.out_dir / style) for style in styles}
    result = {
        "pages": pages,
        "styles": styles,
        "workdir": str(root),
        "run_counts": {s: dict(sorted(c.items())) for s, c in run_counts.items()},
        "library_before": before,
        "library_after": after,
        "template_sources": template_sources,
        "page_results": page_results,
    }
    (args.out_dir / "manifest-pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
