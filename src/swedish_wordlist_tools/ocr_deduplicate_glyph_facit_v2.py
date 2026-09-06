from __future__ import annotations

"""Deduplicate SAOL14 v2 glyph facit without changing glyph semantics.

A duplicate is a model with the same label, semantic role, typographic style,
and exact baseline-relative raster. Provenance (sources), reviewed state and
model_id do not make otherwise identical glyph models distinct.

For each duplicate group the keeper is chosen by:
1. reviewed=true before reviewed=false
2. lowest model_id

Sources from removed duplicates are merged into the keeper. When --apply is
used, both the split store and the monolithic v2 facit are updated so they
continue to represent the same surviving model sequence.

After dedup planning, bit-exact models with the same label but conflicting
 typographic styles are reported separately for manual review. They are never
changed automatically.
"""

import argparse
import json
from pathlib import Path
from typing import Any

FORMAT = "saol14-manual-glyph-facit-v2"


def _model_id_number(row: dict[str, Any]) -> int:
    raw = str(row.get("model_id") or "")
    if not (raw.startswith("g") and raw[1:].isdigit()):
        raise ValueError(f"missing/invalid model_id: {raw!r}")
    return int(raw[1:])


def _model_id_key(path: Path) -> int:
    stem = path.stem
    if not (stem.startswith("g") and stem[1:].isdigit()):
        raise ValueError(f"unexpected split facit filename: {path}")
    return int(stem[1:])


def _load_split(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    meta = json.loads((directory / "_meta.json").read_text(encoding="utf-8"))
    if meta.get("format") != FORMAT:
        raise ValueError(f"unsupported split facit format in {directory / '_meta.json'}")

    rows: list[tuple[Path, dict[str, Any]]] = []
    seen_ids: set[int] = set()
    for path in sorted(directory.rglob("g*.json"), key=_model_id_key):
        file_id = _model_id_key(path)
        row = json.loads(path.read_text(encoding="utf-8"))
        row_id = _model_id_number(row)
        if row_id != file_id:
            raise ValueError(
                f"model id mismatch: {path} contains g{row_id:06d}, filename says g{file_id:06d}"
            )
        if row_id in seen_ids:
            raise ValueError(f"duplicate model_id g{row_id:06d}")
        seen_ids.add(row_id)
        rows.append((path, row))
    return rows


def _load_monolithic(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT:
        raise ValueError(f"unsupported monolithic facit format in {path}")
    return payload


def _pixels(row: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted((int(x), int(y)) for x, y in row.get("pixels_relative_to_baseline") or [])
    )


def _identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("label") or ""),
        str(row.get("role") or "unknown"),
        str(row.get("style") or "roman"),
        _pixels(row),
    )


def _style_conflict_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("label") or ""),
        _pixels(row),
    )


def _source_key(source: Any) -> str:
    return json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merged_sources(rows: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for row in rows:
        for source in row.get("sources") or []:
            key = _source_key(source)
            if key in seen:
                continue
            seen.add(key)
            out.append(source)
    return out


def _choose_keeper(group: list[tuple[Path, dict[str, Any]]]) -> tuple[Path, dict[str, Any]]:
    return min(
        group,
        key=lambda item: (
            not bool(item[1].get("reviewed", False)),
            _model_id_number(item[1]),
        ),
    )


def _monolithic_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _identity(row),
        bool(row.get("reviewed", False)),
        tuple(_source_key(source) for source in row.get("sources") or []),
    )


def _verify_monolithic_matches_split(
    monolithic: dict[str, Any], split_rows: list[tuple[Path, dict[str, Any]]]
) -> None:
    mono_rows = monolithic.get("glyphs") or []
    if len(mono_rows) != len(split_rows):
        raise ValueError(
            f"facit model count differs before dedup: monolithic={len(mono_rows)} split={len(split_rows)}"
        )
    for index, (mono, (_path, split)) in enumerate(zip(mono_rows, split_rows)):
        if _monolithic_signature(mono) != _monolithic_signature(split):
            raise ValueError(
                f"monolithic/split facit differ before dedup at index={index} "
                f"split_model_id={split.get('model_id')!r}"
            )


def _survivors_after_plan(
    split_rows: list[tuple[Path, dict[str, Any]]],
    removed_ids: set[int],
    keeper_rows: dict[int, dict[str, Any]],
) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for path, row in split_rows:
        model_id = _model_id_number(row)
        if model_id in removed_ids:
            continue
        out.append((path, keeper_rows.get(model_id, row)))
    return out


def _report_style_conflicts(rows: list[tuple[Path, dict[str, Any]]]) -> int:
    groups: dict[tuple[Any, ...], list[tuple[Path, dict[str, Any]]]] = {}
    for item in rows:
        groups.setdefault(_style_conflict_identity(item[1]), []).append(item)

    conflicts = [
        group
        for group in groups.values()
        if len(group) > 1
        and len({str(row.get("style") or "roman") for _path, row in group}) > 1
    ]
    conflicts.sort(key=lambda group: min(_model_id_number(row) for _path, row in group))

    for index, group in enumerate(conflicts, start=1):
        first = group[0][1]
        label = str(first.get("label") or "")
        pixel_count = len(_pixels(first))
        styles = sorted({str(row.get("style") or "roman") for _path, row in group})
        print(
            f"style-conflict: n={index} label={label!r} pixels={pixel_count} "
            f"styles={','.join(styles)} models={len(group)}",
            flush=True,
        )
        for path, row in sorted(group, key=lambda item: _model_id_number(item[1])):
            model_id = _model_id_number(row)
            reviewed = bool(row.get("reviewed", False))
            role = str(row.get("role") or "unknown")
            style = str(row.get("style") or "roman")
            sources = row.get("sources") or []
            source_summaries: list[str] = []
            for source in sources[:3]:
                if isinstance(source, dict):
                    page = source.get("page")
                    word = source.get("expected_word") or source.get("jsonl_word") or source.get("source_id")
                    parts = []
                    if page is not None:
                        parts.append(f"p{page}")
                    if word:
                        parts.append(str(word))
                    source_summaries.append(":".join(parts) if parts else _source_key(source))
                else:
                    source_summaries.append(str(source))
            if len(sources) > 3:
                source_summaries.append(f"+{len(sources) - 3} more")
            print(
                f"  model=g{model_id:06d}{'*' if reviewed else ''} style={style} role={role} "
                f"sources={len(sources)} path={path}"
                + (f" source=[{' | '.join(source_summaries)}]" if source_summaries else ""),
                flush=True,
            )

    print(f"style-conflict-summary: groups={len(conflicts)}", flush=True)
    return len(conflicts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Deduplicate SAOL14 v2 glyph facit safely.")
    ap.add_argument("--facit", type=Path, required=True, help="monolithic v2 facit")
    ap.add_argument("--split-facit", type=Path, required=True, help="split facit-v2 directory")
    ap.add_argument("--apply", action="store_true", help="rewrite/delete files; default is dry-run")
    args = ap.parse_args()

    monolithic = _load_monolithic(args.facit)
    split_rows = _load_split(args.split_facit)
    _verify_monolithic_matches_split(monolithic, split_rows)

    groups: dict[tuple[Any, ...], list[tuple[Path, dict[str, Any]]]] = {}
    for item in split_rows:
        groups.setdefault(_identity(item[1]), []).append(item)

    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    duplicate_groups.sort(key=lambda group: min(_model_id_number(row) for _path, row in group))

    removed_ids: set[int] = set()
    keeper_rows: dict[int, dict[str, Any]] = {}
    reviewed_promotions = 0

    for group_index, group in enumerate(duplicate_groups, start=1):
        keeper_path, keeper = _choose_keeper(group)
        keeper_id = _model_id_number(keeper)
        any_reviewed = any(bool(row.get("reviewed", False)) for _path, row in group)
        if any_reviewed and not bool(keeper.get("reviewed", False)):
            raise AssertionError("reviewed keeper selection failed")
        if any_reviewed and any(not bool(row.get("reviewed", False)) for _path, row in group):
            reviewed_promotions += 1

        merged = dict(keeper)
        merged["reviewed"] = any_reviewed
        merged["sources"] = _merged_sources([row for _path, row in group])
        keeper_rows[keeper_id] = merged

        removed = sorted(
            (_model_id_number(row), path, bool(row.get("reviewed", False)))
            for path, row in group
            if _model_id_number(row) != keeper_id
        )
        removed_ids.update(model_id for model_id, _path, _reviewed in removed)

        label = str(keeper.get("label") or "")
        role = str(keeper.get("role") or "unknown")
        style = str(keeper.get("style") or "roman")
        ids = ",".join(
            f"g{_model_id_number(row):06d}{'*' if row.get('reviewed', False) else ''}"
            for _path, row in sorted(group, key=lambda item: _model_id_number(item[1]))
        )
        print(
            f"duplicate-group: n={group_index} label={label!r} role={role} style={style} "
            f"models=[{ids}] keep=g{keeper_id:06d}{'*' if any_reviewed else ''} "
            f"remove={len(removed)} merged_sources={len(merged['sources'])}",
            flush=True,
        )

    print(
        f"dedup-summary: models_before={len(split_rows)} duplicate_groups={len(duplicate_groups)} "
        f"remove={len(removed_ids)} models_after={len(split_rows) - len(removed_ids)} "
        f"reviewed_wins={reviewed_promotions} mode={'apply' if args.apply else 'dry-run'}",
        flush=True,
    )

    planned_survivors = _survivors_after_plan(split_rows, removed_ids, keeper_rows)
    _report_style_conflicts(planned_survivors)

    if not args.apply:
        return 0

    surviving_rows: list[dict[str, Any]] = []
    for path, row in split_rows:
        model_id = _model_id_number(row)
        if model_id in removed_ids:
            path.unlink()
            continue
        final_row = keeper_rows.get(model_id, row)
        if final_row is not row:
            path.write_text(
                json.dumps(final_row, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        surviving_rows.append(final_row)

    rewritten = dict(monolithic)
    rewritten["glyphs"] = [
        {key: value for key, value in row.items() if key != "model_id"}
        for row in surviving_rows
    ]
    args.facit.write_text(
        json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Re-read and verify counts/ordering after the mutation.
    final_split = _load_split(args.split_facit)
    final_mono = _load_monolithic(args.facit)
    _verify_monolithic_matches_split(final_mono, final_split)
    remaining_groups: dict[tuple[Any, ...], int] = {}
    for _path, row in final_split:
        key = _identity(row)
        remaining_groups[key] = remaining_groups.get(key, 0) + 1
    still_duplicate = sum(1 for count in remaining_groups.values() if count > 1)
    if still_duplicate:
        raise AssertionError(f"dedup left {still_duplicate} duplicate groups")

    print(
        f"dedup-applied: models={len(final_split)} monolithic=split order=identical duplicates=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
