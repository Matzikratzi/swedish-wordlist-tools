from __future__ import annotations

"""Compare two captured SAOL14 OCR baselines row for row."""

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict[tuple[int, int, int], dict]:
    rows = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (int(row["page"]), int(row["column"]), int(row["row"]))
            if key in rows:
                raise ValueError(f"duplicate row {key} in {path}")
            rows[key] = row
    return rows


def _stable(row: dict) -> dict:
    """Fields whose equality defines OCR-result neutrality."""
    return {
        key: row.get(key)
        for key in (
            "crop_box", "baseline", "covered_pixels", "source_pixels",
            "fully_exact", "needs_work", "unreviewed_matches", "text", "matches",
        )
    }


def compare(reference: Path, candidate: Path) -> list[dict]:
    before, after = _load(reference), _load(candidate)
    diffs = []
    for key in sorted(before.keys() | after.keys()):
        if key not in before:
            diffs.append({"row": key, "kind": "added"})
        elif key not in after:
            diffs.append({"row": key, "kind": "removed"})
        elif _stable(before[key]) != _stable(after[key]):
            diffs.append({"row": key, "kind": "changed", "before": _stable(before[key]), "after": _stable(after[key])})
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare captured OCR rows against a frozen baseline")
    ap.add_argument("reference", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    diffs = compare(args.reference, args.candidate)
    if args.output:
        args.output.write_text(json.dumps({"differences": diffs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"baseline-diff: differences={len(diffs)}")
    for diff in diffs[:20]:
        print(f"baseline-diff: {diff['kind']} row={tuple(diff['row'])}")
    if len(diffs) > 20:
        print(f"baseline-diff: ... {len(diffs)-20} more")
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
