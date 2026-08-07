from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
TARGET_STATUS = "form_set_mismatch"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def select_rows(
    rows: Iterable[dict[str, Any]],
    *,
    upos: str | None = None,
    notation: str | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    wanted_upos = upos.upper() if upos else None
    for row in rows:
        if str(row.get("status", "")) != TARGET_STATUS:
            continue
        if wanted_upos is not None and str(row.get("upos", "")).upper() != wanted_upos:
            continue
        if notation is not None and str(row.get("notation", "")) != notation:
            continue
        selected.append(row)
    selected.sort(
        key=lambda row: (
            str(row.get("lemma", "")).casefold(),
            str(row.get("homonym_number", "")),
        )
    )
    return selected


def render_rows(rows: Iterable[dict[str, Any]]) -> str:
    rows = list(rows)
    lines = [f"Poster: {len(rows)}"]
    for row in rows:
        lines.extend(
            [
                "",
                f"{row.get('lemma', '')} (homonr={row.get('homonym_number', '')})",
                f"  upos: {row.get('upos', '')}",
                f"  notation: {row.get('notation', '') or '(null)'}",
                f"  record_id: {row.get('record_id', '')}",
                f"  generator: {row.get('generator', '')}",
                f"  match_method: {row.get('match_method', '')}",
                "  SAOL-generator: " + ", ".join(map(str, row.get("generated_forms", ()))),
                "  SALDO: " + ", ".join(map(str, row.get("saldo_forms", ()))),
                "  Extra från SAOL: " + (", ".join(map(str, row.get("extra_from_saol", ()))) or "–"),
                "  Saknas från SAOL: " + (", ".join(map(str, row.get("missing_from_saol", ()))) or "–"),
            ]
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Visa hela SAOL- och SALDO-formmängden för en aktuell formmismatchgrupp"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--upos")
    parser.add_argument("--notation")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = select_rows(read_jsonl(args.input), upos=args.upos, notation=args.notation)
    print(render_rows(rows), end="")


if __name__ == "__main__":
    main()
