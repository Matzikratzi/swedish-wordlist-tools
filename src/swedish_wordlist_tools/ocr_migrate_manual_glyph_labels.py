from __future__ import annotations

import argparse
import json
from pathlib import Path


# Manual review originally copied JSONL's '+' notation for the printed tilde.
# The glyph facit should instead describe what is actually printed on the page.
LABEL_MIGRATIONS = {
    ("+", "italic"): "~",
}


def migrate_payload(payload: dict) -> tuple[dict, int]:
    changed = 0
    for glyph in payload.get("glyphs") or []:
        key = (str(glyph.get("label") or ""), str(glyph.get("style") or ""))
        replacement = LABEL_MIGRATIONS.get(key)
        if replacement is None:
            continue
        glyph["label"] = replacement
        changed += 1
    return payload, changed


def migrate_file(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload, changed = migrate_payload(payload)
    if changed:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate old manual SAOL glyph labels to literal printed notation.")
    ap.add_argument("facit", nargs="+", type=Path)
    args = ap.parse_args()
    total = 0
    for path in args.facit:
        changed = migrate_file(path)
        total += changed
        print(f"{path}: changed={changed}")
    print(f"total_changed={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
