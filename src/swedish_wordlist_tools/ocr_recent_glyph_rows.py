from __future__ import annotations

import argparse
import json
from pathlib import Path


def recent_source_rows(facit: Path, limit: int = 20) -> list[dict]:
    """Return the most recently appended unique glyph source rows.

    The manual facit is append-oriented, so reverse glyph order is the best
    available history of recent manual fixes. Multiple glyphs created from the
    same physical row are collapsed into one entry, preserving newest-first
    order and collecting all labels/styles seen for that row.
    """
    data = json.loads(facit.read_text())
    glyphs = data.get("glyphs", []) if isinstance(data, dict) else data
    rows: list[dict] = []
    by_key: dict[tuple[int, int, int], dict] = {}

    for glyph in reversed(glyphs):
        label = str(glyph.get("label", ""))
        style = str(glyph.get("style", ""))
        for source in reversed(glyph.get("sources") or []):
            try:
                key = (int(source["page"]), int(source["column"]), int(source["row"]))
            except (KeyError, TypeError, ValueError):
                continue
            entry = by_key.get(key)
            if entry is None:
                if len(rows) >= limit:
                    continue
                entry = {
                    "page": key[0],
                    "column": key[1],
                    "row": key[2],
                    "glyphs": [],
                }
                by_key[key] = entry
                rows.append(entry)
            glyph_id = (label, style)
            if glyph_id not in entry["glyphs"]:
                entry["glyphs"].append(glyph_id)

    return rows


def editor_command(jsonl: Path, entry: dict, *, port: int = 8766) -> str:
    return (
        "PYTHONPATH=src python -m "
        "swedish_wordlist_tools.ocr_review_five_rows_glyphs_boundary_html "
        f"{jsonl} --page {entry['page']} --column {entry['column']} "
        f"--row {entry['row']} --port {port}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Show recently added/fixed glyph source rows, newest first."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument(
        "--commands",
        action="store_true",
        help="print a ready-to-run ordinary editor command after every row",
    )
    args = ap.parse_args()

    rows = recent_source_rows(args.facit, args.limit)
    if not rows:
        print("Inga källrader hittades i facit.")
        return 0

    for index, entry in enumerate(rows, start=1):
        glyphs = ", ".join(
            f"{label!r}/{style}" if style else repr(label)
            for label, style in entry["glyphs"]
        )
        print(
            f"{index:2d}. page={entry['page']} col={entry['column']} row={entry['row']}"
            + (f"  glyphs={glyphs}" if glyphs else "")
        )
        if args.commands:
            print("    " + editor_command(args.jsonl, entry, port=args.port))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
