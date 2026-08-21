from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .ocr_mine_jsonl_pages import _crop_columns, _download, _inventory, _ocr_tsv, _parse_pages, _source_for_page


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine SAOL glyph templates with style-aware form-token selection.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--styles", default="italic,bold,roman")
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
        for idx, column in enumerate(columns, 1):
            tsv = page_dir / f"column-{idx}.tsv"
            _ocr_tsv(column, tsv)
            style_results = {}
            for style in styles:
                cmd = [
                    sys.executable, "-m", "swedish_wordlist_tools.ocr_mine_jsonl_templates_styled",
                    str(args.jsonl), str(column), str(tsv), "--page", str(page),
                    "--chars", args.chars, "--out-dir", str(args.out_dir),
                    "--limit-per-char", str(args.limit_per_char), "--style", style,
                ]
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
                for item in data.get("templates", []):
                    output = item.get("output")
                    bbox = item.get("bbox")
                    if isinstance(output, str) and isinstance(bbox, list | tuple):
                        template_sources[output] = {
                            "page": page,
                            "column": idx,
                            "bbox": list(bbox),
                            "column_image": str(column),
                            "source": source,
                        }
                style_results[style] = {
                    "matched_entries": data.get("matched_entries"),
                    "exact_word_matches": data.get("exact_word_matches"),
                    "counts": counts,
                    "rejected_fuzzy_words": data.get("rejected_fuzzy_words"),
                    "rejected_charbox_count": data.get("rejected_charbox_count"),
                    "rejected_charbox_labels": data.get("rejected_charbox_labels"),
                    "rejected_geometry": data.get("rejected_geometry"),
                }
            column_results.append({"column": idx, "styles": style_results})
        page_results.append({"page": page, "columns": column_results})

    after = {style: _inventory(args.out_dir / style) for style in styles}
    result = {
        "pages": pages,
        "styles": styles,
        "run_counts": {s: dict(sorted(c.items())) for s, c in run_counts.items()},
        "library_before": before,
        "library_after": after,
        "page_results": page_results,
        "template_sources": template_sources,
    }
    (args.out_dir / "manifest-pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    if owned is not None:
        owned.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
