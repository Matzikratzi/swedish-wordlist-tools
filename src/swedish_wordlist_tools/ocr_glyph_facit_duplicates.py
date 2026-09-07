from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .ocr_glyph_facit_store import CANONICAL_AGGREGATE_NAME, build_facit, load_split_facit, write_split_facit


def _pixels(glyph: dict) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(x), int(y)) for x, y in glyph.get("pixels_relative_to_baseline") or []))


def _typography(glyph: dict) -> str:
    return str(glyph.get("style") or "roman")


def _semantic_key(glyph: dict) -> tuple[str, str, tuple[tuple[int, int], ...]]:
    """Identity for safe deduplication; role is intentionally irrelevant."""
    return (str(glyph.get("label") or ""), _typography(glyph), _pixels(glyph))


def _raster_key(glyph: dict) -> tuple[tuple[int, int], ...]:
    return _pixels(glyph)


def _model_id_number(glyph: dict) -> int:
    text = str(glyph.get("model_id") or "")
    return int(text[1:]) if text.startswith("g") and text[1:].isdigit() else 10**12


def preferred_model(group: list[dict]) -> dict:
    """Prefer reviewed models, then the stable lowest model_id."""
    return min(group, key=lambda glyph: (not bool(glyph.get("reviewed", False)), _model_id_number(glyph)))


def audit_duplicates(payload: dict) -> dict:
    glyphs = list(payload.get("glyphs") or [])
    semantic_groups: dict[tuple, list[dict]] = defaultdict(list)
    raster_groups: dict[tuple, list[dict]] = defaultdict(list)
    for glyph in glyphs:
        semantic_groups[_semantic_key(glyph)].append(glyph)
        raster_groups[_raster_key(glyph)].append(glyph)

    duplicates = []
    for group in semantic_groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_model_id_number)
        keep = preferred_model(ordered)
        duplicates.append({
            "label": str(keep.get("label") or ""),
            "style": _typography(keep),
            "pixels": len(_pixels(keep)),
            "keep": keep,
            "remove": [glyph for glyph in ordered if glyph is not keep],
            "models": ordered,
        })

    ambiguities = []
    cross_typography = []
    for group in raster_groups.values():
        if len(group) < 2:
            continue
        semantic = {(str(g.get("label") or ""), _typography(g)) for g in group}
        if len(semantic) < 2:
            continue
        item = {"pixels": len(_pixels(group[0])), "models": sorted(group, key=_model_id_number)}
        ambiguities.append(item)
        labels = {str(g.get("label") or "") for g in group}
        styles = {_typography(g) for g in group}
        if len(labels) == 1 and len(styles) > 1:
            cross_typography.append(item)

    duplicates.sort(key=lambda item: (item["label"], item["style"], _model_id_number(item["keep"])))
    ambiguities.sort(key=lambda item: (_model_id_number(item["models"][0]), item["pixels"]))
    cross_typography.sort(key=lambda item: (_model_id_number(item["models"][0]), item["pixels"]))
    return {
        "models": len(glyphs),
        "duplicate_groups": duplicates,
        "duplicate_models_removable": sum(len(item["remove"]) for item in duplicates),
        "raster_ambiguity_groups": ambiguities,
        "cross_typography_groups": cross_typography,
    }


def _merge_sources(keep: dict, removed: list[dict]) -> None:
    merged = []
    seen = set()
    for glyph in [keep, *removed]:
        for source in glyph.get("sources") or []:
            key = json.dumps(source, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    keep["sources"] = merged
    keep["reviewed"] = any(bool(g.get("reviewed", False)) for g in [keep, *removed])


def deduplicate_payload(payload: dict) -> dict:
    """Remove only exact label+typography+baseline-raster duplicates."""
    report = audit_duplicates(payload)
    remove_ids: set[str] = set()
    for item in report["duplicate_groups"]:
        _merge_sources(item["keep"], item["remove"])
        remove_ids.update(str(g.get("model_id")) for g in item["remove"])
    payload["glyphs"] = [g for g in payload.get("glyphs") or [] if str(g.get("model_id")) not in remove_ids]
    return report


def _model_text(glyph: dict) -> str:
    reviewed = "verified" if bool(glyph.get("reviewed", False)) else "UNVERIFIED"
    return f"{glyph.get('model_id')} {glyph.get('label')!r}/{_typography(glyph)} {reviewed} sources={len(glyph.get('sources') or [])}"


def _raster_ascii(glyph: dict) -> list[str]:
    """Render the exact baseline-relative model; y=0 is visibly marked."""
    points = set(_pixels(glyph))
    if not points:
        return ["    (tom raster)"]
    min_x = min(x for x, _y in points)
    max_x = max(x for x, _y in points)
    min_y = min(min(y for _x, y in points), 0)
    max_y = max(max(y for _x, y in points), 0)
    lines = []
    for y in range(min_y, max_y + 1):
        marker = ">" if y == 0 else " "
        raster = "".join("#" if (x, y) in points else "." for x in range(min_x, max_x + 1))
        suffix = "  <- baseline y=0" if y == 0 else ""
        lines.append(f"    {marker} {y:>3} {raster}{suffix}")
    return lines


def _render_cross_typography(report: dict) -> list[str]:
    groups = report.get("cross_typography_groups") or []
    lines = [f"\nSAMMA LABEL + PIXLAR + BASLINJE, MEN OLIKA TYPOGRAFI: {len(groups)} grupper"]
    for index, item in enumerate(groups, 1):
        lines.append(f"[{index}] {item['pixels']} px — LÄMNAS ORÖRD")
        for glyph in item["models"]:
            lines.append("  " + _model_text(glyph))
        lines.append("  exakt gemensamt baslinjerelativt raster (#=svart, .=vit):")
        lines.extend(_raster_ascii(item["models"][0]))
    return lines


def render_report(report: dict) -> str:
    lines = [
        f"modeller: {report['models']}",
        f"verkliga duplikatgrupper: {len(report['duplicate_groups'])}",
        f"modeller som kan tas bort: {report['duplicate_models_removable']}",
        f"pixelidentiska men label/typografi-olika grupper: {len(report['raster_ambiguity_groups'])}",
    ]
    if report["duplicate_groups"]:
        lines.append("\nVERKLIGA DUPLIKAT — SAMMA LABEL, TYPOGRAFI, PIXLAR OCH BASLINJE")
        for index, item in enumerate(report["duplicate_groups"], 1):
            lines.append(f"[{index}] {item['label']!r}/{item['style']} {item['pixels']} px")
            lines.append("  KEEP   " + _model_text(item["keep"]))
            for glyph in item["remove"]:
                lines.append("  REMOVE " + _model_text(glyph))
    lines.extend(_render_cross_typography(report))
    other = [item for item in report["raster_ambiguity_groups"] if item not in report["cross_typography_groups"]]
    if other:
        lines.append("\nPIXEL- OCH BASLINJEIDENTISKA MEN OLIKA LABEL — RADERA INTE AUTOMATISKT")
        for index, item in enumerate(other, 1):
            lines.append(f"[{index}] {item['pixels']} px")
            for glyph in item["models"]:
                lines.append("  " + _model_text(glyph))
    return "\n".join(lines) + "\n"


def apply_dedup(store: Path, aggregate: Path) -> str:
    payload = load_split_facit(store)
    report = deduplicate_payload(payload)
    before = report["models"]
    removed = report["duplicate_models_removable"]
    write_split_facit(payload, store)
    build_facit(store, aggregate)
    lines = [
        f"dedup: {before} -> {before - removed} modeller; {removed} redundanta modeller borttagna",
        f"aggregate ombyggd: {aggregate}",
    ]
    lines.extend(_render_cross_typography(report))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit or safely deduplicate baseline-relative glyph facit; role is ignored")
    parser.add_argument("store", type=Path, nargs="?", default=Path("glyphs/facit-v2"))
    parser.add_argument("--apply", action="store_true", help="remove only exact same-label/same-typography duplicates")
    parser.add_argument("--aggregate", type=Path, help="compatibility aggregate to rebuild after --apply")
    args = parser.parse_args(argv)
    if args.apply:
        aggregate = args.aggregate or args.store.parent / CANONICAL_AGGREGATE_NAME
        print(apply_dedup(args.store, aggregate), end="")
        return 0
    payload = load_split_facit(args.store)
    print(render_report(audit_duplicates(payload)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
