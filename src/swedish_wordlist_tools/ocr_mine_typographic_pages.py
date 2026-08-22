from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .ocr_mine_jsonl_pages import _crop_columns, _download, _ocr_tsv, _parse_pages, _source_for_page


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine mixed italic/roman SAOL glyphs across facsimile pages.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--keep-workdir", type=Path)
    ap.add_argument("--limit-per-char", type=int, default=30)
    args = ap.parse_args()

    pages = _parse_pages(args.pages)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    owned = None
    if args.keep_workdir:
        root = args.keep_workdir
        root.mkdir(parents=True, exist_ok=True)
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-typographic-pages-")
        root = Path(owned.name)

    totals: dict[str, dict[str, int]] = {"italic": {}, "roman": {}}
    sources: dict[str, dict[str, object]] = {}
    page_results = []
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
        col_results = []
        for colno, (column, column_left) in enumerate(columns, 1):
            tsv = page_dir / f"column-{colno}.tsv"
            _ocr_tsv(column, tsv)
            cmd = [
                sys.executable, "-m", "swedish_wordlist_tools.ocr_mine_typographic_text_templates",
                str(args.jsonl), str(column), str(tsv), "--page", str(page),
                "--out-dir", str(args.out_dir), "--limit-per-char", str(args.limit_per_char),
            ]
            proc = subprocess.run(cmd, text=True, capture_output=True)
            if proc.returncode != 0:
                col_results.append({"column": colno, "error": proc.stderr.strip() or proc.stdout.strip()})
                continue
            data = json.loads(proc.stdout)
            for style, counts in data.get("counts", {}).items():
                for ch, n in counts.items():
                    totals.setdefault(style, {})[ch] = totals.setdefault(style, {}).get(ch, 0) + int(n)
            for item in data.get("templates", []):
                output = item.get("output")
                bbox = item.get("bbox")
                if not output or not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                sources[str(output)] = {
                    "page": page, "column": colno, "column_left": column_left,
                    "bbox": bbox,
                    "page_bbox": [int(bbox[0])+column_left, int(bbox[1]), int(bbox[2]), int(bbox[3])],
                    "source": source, "page_image": str(image), "column_image": str(column),
                    "subnr": item.get("subnr"), "source_word": item.get("source_word"),
                    "expected_word": item.get("expected_word"), "position_kind": item.get("position_kind"),
                    "style": item.get("style"), "character": item.get("character"),
                }
            col_results.append({
                "column": colno,
                "counts": data.get("counts", {}),
                "matched_entries": data.get("matched_entries"),
                "exact_tokens": data.get("exact_tokens"),
                "rejected_charbox_count": data.get("rejected_charbox_count"),
                "rejected_charbox_labels": data.get("rejected_charbox_labels"),
            })
        page_results.append({"page": page, "source": source, "columns": col_results})

    result = {
        "pages": pages,
        "counts": {s: dict(sorted(v.items())) for s, v in totals.items()},
        "template_sources": sources,
        "page_results": page_results,
        "notes": {"plus_printed_as": "~", "square_brackets": "excluded"},
    }
    (args.out_dir / "manifest-pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
