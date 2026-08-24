from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .ocr_mine_jsonl_pages import _crop_columns, _download, _inventory, _ocr_tsv, _parse_pages, _source_for_page


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine glyphs from verified bold SAOL headwords, using JSONL labels and Tesseract box geometry."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--keep-workdir", type=Path)
    parser.add_argument("--limit-per-char", type=int, default=20)
    args = parser.parse_args()

    pages = _parse_pages(args.pages)
    style = "bold"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    before = {style: _inventory(args.out_dir / style)}

    owned = None
    if args.keep_workdir:
        root = args.keep_workdir
        root.mkdir(parents=True, exist_ok=True)
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-bold-headword-pages-")
        root = Path(owned.name)

    run_counts: dict[str, dict[str, int]] = {style: {}}
    page_results: list[dict[str, object]] = []
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
            cmd = [
                sys.executable,
                "-m",
                "swedish_wordlist_tools.ocr_mine_jsonl_templates_bold_initials",
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
                "--style",
                style,
                "--bold-all-chars",
            ]
            proc = subprocess.run(cmd, text=True, capture_output=True)
            if proc.returncode != 0:
                column_results.append(
                    {"column": idx, "column_left": column_left, "styles": {style: {"error": proc.stderr.strip() or proc.stdout.strip()}}}
                )
                continue
            data = json.loads(proc.stdout)
            counts = data.get("counts", {})
            for ch, n in counts.items():
                d = run_counts[style]
                d[str(ch)] = d.get(str(ch), 0) + int(n)
            for item in data.get("templates", []):
                output = item.get("output")
                bbox = item.get("bbox")
                if isinstance(output, str) and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    page_bbox = [int(bbox[0]) + column_left, int(bbox[1]), int(bbox[2]), int(bbox[3])]
                    template_sources[output] = {
                        "page": page,
                        "column": idx,
                        "column_left": column_left,
                        "bbox": list(bbox),
                        "page_bbox": page_bbox,
                        "column_image": str(column),
                        "page_image": str(image),
                        "source": source,
                        "subnr": item.get("subnr"),
                        "source_word": item.get("source_word"),
                        "expected_word": item.get("expected_word"),
                        "position_kind": item.get("position_kind"),
                        "style": style,
                        "character": item.get("character"),
                    }
            column_results.append(
                {
                    "column": idx,
                    "column_left": column_left,
                    "styles": {
                        style: {
                            "matched_entries": data.get("matched_entries"),
                            "exact_word_matches": data.get("exact_word_matches"),
                            "counts": counts,
                            "rejected_fuzzy_words": data.get("rejected_fuzzy_words"),
                            "rejected_charbox_count": data.get("rejected_charbox_count"),
                            "rejected_charbox_labels": data.get("rejected_charbox_labels"),
                            "rejected_geometry": data.get("rejected_geometry"),
                        }
                    },
                }
            )
        page_results.append({"page": page, "source": source, "columns": column_results})

    after = {style: _inventory(args.out_dir / style)}
    result = {
        "pages": pages,
        "styles": [style],
        "run_counts": {style: dict(sorted(run_counts[style].items()))},
        "library_before": before,
        "library_after": after,
        "page_results": page_results,
        "template_sources": template_sources,
    }
    (args.out_dir / "manifest-pages-bold-headwords.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    if owned is not None:
        owned.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
