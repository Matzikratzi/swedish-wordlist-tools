from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_page_glyph_audit import _load_review_state_for_audit
from .ocr_review_batch_defects_html import editor_argv
from .ocr_review_five_rows_glyphs_fast_html import build_page_context


def load_manifest(path: Path) -> list[dict]:
    records = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {lineno}: {exc}") from exc
        records.append(record)
    return records


def first_unresolved(jsonl: Path, records: list[dict], models, *, threshold: int):
    contexts: dict[int, dict] = {}
    for index, record in enumerate(records):
        page = int(record["page"])
        position = (int(record["column"]), int(record["row"]))
        context = contexts.get(page)
        if context is None:
            context = build_page_context(jsonl, page, threshold)
            contexts[page] = context
        if position not in context.get("positions", []):
            print(f"manifest: hoppar över saknad rad page={page} col={position[0]} row={position[1]}", flush=True)
            continue
        state = _load_review_state_for_audit(context, position, models)
        unknown = max(0, int(state.get("source_pixels") or 0) - int(state.get("covered_pixels") or 0))
        if unknown:
            return index, record, unknown
        print(f"manifest: redan fixad page={page} col={position[0]} row={position[1]}", flush=True)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read a saved OCR defect manifest, skip rows already fixed by the current facit, and open the next unresolved row."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--commands", action="store_true", help="print editor commands for all manifest rows instead of opening one")
    args = ap.parse_args()

    records = load_manifest(args.manifest)
    if args.commands:
        for record in records:
            argv = editor_argv(
                args.jsonl,
                page=int(record["page"]),
                position=(int(record["column"]), int(record["row"])),
                threshold=args.threshold,
                facit=args.facit,
                host=args.host,
                port=args.port,
                no_browser=args.no_browser,
            )
            print("PYTHONPATH=src python -m swedish_wordlist_tools." + " ".join(argv))
        return 0

    models = load_facit(args.facit)
    found = first_unresolved(args.jsonl, records, models, threshold=args.threshold)
    if found is None:
        print(f"manifest: alla {len(records)} noterade rader är nu pixel-exakta", flush=True)
        return 0

    index, record, unknown = found
    page = int(record["page"])
    position = (int(record["column"]), int(record["row"]))
    print(
        f"manifest: nästa fel {index + 1}/{len(records)} page={page} col={position[0]} row={position[1]} "
        f"unknown={unknown} text={record.get('text', '')!r}",
        flush=True,
    )
    argv = [
        sys.executable,
        "-m",
        "swedish_wordlist_tools.ocr_review_five_rows_glyphs_boundary_html",
        str(args.jsonl),
        "--page", str(page),
        "--column", str(position[0]),
        "--row", str(position[1]),
        "--threshold", str(args.threshold),
        "--facit", str(args.facit),
        "--host", str(args.host),
        "--port", str(args.port),
    ]
    if args.no_browser:
        argv.append("--no-browser")
    return subprocess.call(argv)


if __name__ == "__main__":
    raise SystemExit(main())
