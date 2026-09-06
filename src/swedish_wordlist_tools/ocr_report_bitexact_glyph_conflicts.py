from __future__ import annotations

"""Report bit-exact glyph models whose metadata disagree.

Models are grouped solely by their baseline-relative pixel raster.  A group is
reported when two or more surviving models have different label, role or
style.  This tool is diagnostic only and never rewrites the facit.
"""

import argparse
from pathlib import Path
from typing import Any

from .ocr_deduplicate_glyph_facit_v2 import (
    _load_monolithic,
    _load_split,
    _model_id_number,
    _pixels,
    _source_key,
    _verify_monolithic_matches_split,
)


def _metadata(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("label") or ""),
        str(row.get("role") or "unknown"),
        str(row.get("style") or "roman"),
    )


def _source_summary(source: Any) -> str:
    if not isinstance(source, dict):
        return str(source)
    page = source.get("page")
    word = (
        source.get("expected_word")
        or source.get("jsonl_word")
        or source.get("source_id")
    )
    parts: list[str] = []
    if page is not None:
        parts.append(f"p{page}")
    if word:
        parts.append(str(word))
    return ":".join(parts) if parts else _source_key(source)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report bit-exact SAOL glyph models with conflicting metadata."
    )
    ap.add_argument("--facit", type=Path, required=True, help="monolithic v2 facit")
    ap.add_argument("--split-facit", type=Path, required=True, help="split facit-v2 directory")
    args = ap.parse_args()

    monolithic = _load_monolithic(args.facit)
    rows = _load_split(args.split_facit)
    _verify_monolithic_matches_split(monolithic, rows)

    groups: dict[tuple[tuple[int, int], ...], list[tuple[Path, dict[str, Any]]]] = {}
    for item in rows:
        groups.setdefault(_pixels(item[1]), []).append(item)

    conflicts = [
        group
        for group in groups.values()
        if len(group) > 1 and len({_metadata(row) for _path, row in group}) > 1
    ]
    conflicts.sort(
        key=lambda group: min(_model_id_number(row) for _path, row in group)
    )

    for index, group in enumerate(conflicts, start=1):
        first = group[0][1]
        labels = sorted({str(row.get("label") or "") for _path, row in group})
        roles = sorted({str(row.get("role") or "unknown") for _path, row in group})
        styles = sorted({str(row.get("style") or "roman") for _path, row in group})
        print(
            f"bitexact-conflict: n={index} pixels={len(_pixels(first))} models={len(group)} "
            f"labels={labels!r} roles={roles!r} styles={styles!r}",
            flush=True,
        )
        for path, row in sorted(group, key=lambda item: _model_id_number(item[1])):
            model_id = _model_id_number(row)
            reviewed = bool(row.get("reviewed", False))
            label, role, style = _metadata(row)
            sources = row.get("sources") or []
            shown = [_source_summary(source) for source in sources[:4]]
            if len(sources) > 4:
                shown.append(f"+{len(sources) - 4} more")
            print(
                f"  model=g{model_id:06d}{'*' if reviewed else ''} "
                f"label={label!r} role={role} style={style} sources={len(sources)} "
                f"path={path}"
                + (f" source=[{' | '.join(shown)}]" if shown else ""),
                flush=True,
            )

    print(f"bitexact-conflict-summary: groups={len(conflicts)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
