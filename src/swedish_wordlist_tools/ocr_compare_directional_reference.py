from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


_ROW_RE = re.compile(
    r"^directional-row: row=(?P<row>\d+) .*?status=(?P<status>\S+).*?"
    r"text=(?P<text>.+?) remaining=(?P<remaining>\d+)"
)


def _load_reference(path: Path, *, page: int, column: int) -> dict[int, str]:
    rows: dict[int, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            if int(record.get("page", -1)) != page:
                continue
            if int(record.get("column", -1)) != column:
                continue
            row = int(record["row"])
            rows[row] = "".join(str(match["label"]) for match in record.get("matches", ()))
    return rows


def _load_directional(path: Path) -> dict[int, tuple[str, str, int]]:
    rows: dict[int, tuple[str, str, int]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = _ROW_RE.match(line.rstrip("\n"))
            if match is None:
                continue
            row = int(match.group("row"))
            text = ast.literal_eval(match.group("text"))
            rows[row] = (str(text), match.group("status"), int(match.group("remaining")))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare directional OCR benchmark output with the conservative OCR reference. "
            "Comparison is glyph-for-glyph using reference matches[].label, so inserted spaces "
            "in the reference text field do not affect the result."
        )
    )
    ap.add_argument("benchmark_log", type=Path)
    ap.add_argument("reference_rows", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, default=0)
    args = ap.parse_args()

    reference = _load_reference(args.reference_rows, page=args.page, column=args.column)
    directional = _load_directional(args.benchmark_log)

    if not reference:
        raise SystemExit(f"no reference rows for page={args.page} column={args.column}")
    if not directional:
        raise SystemExit(f"no directional-row lines found in {args.benchmark_log}")

    equal = 0
    different = 0
    missing = 0

    for row in sorted(directional):
        actual, status, remaining = directional[row]
        expected = reference.get(row)
        if expected is None:
            missing += 1
            print(f"reference-missing: row={row} actual={actual!r} status={status}")
            continue
        if actual == expected:
            equal += 1
            print(
                f"reference-ok: row={row} glyphs={len(actual)} status={status} remaining={remaining}"
            )
            continue
        different += 1
        common = 0
        for actual_char, expected_char in zip(actual, expected):
            if actual_char != expected_char:
                break
            common += 1
        print(
            f"reference-diff: row={row} common_prefix={common} status={status} remaining={remaining}\n"
            f"  expected={expected!r}\n"
            f"  actual  ={actual!r}"
        )

    not_run = sorted(set(reference) - set(directional))
    print(
        f"reference-summary: page={args.page} column={args.column} compared={len(directional)} "
        f"equal={equal} different={different} reference_missing={missing} "
        f"reference_rows_not_run={len(not_run)}"
    )
    if not_run:
        print(f"reference-not-run: rows={not_run}")

    return 1 if different or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
