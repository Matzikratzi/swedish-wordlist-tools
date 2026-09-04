from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from .ocr_glyph_facit_store import load_split_facit


def _pixels(glyph: dict) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(x), int(y)) for x, y in glyph.get("pixels_relative_to_baseline") or []))


def _typography(glyph: dict) -> str:
    return str(glyph.get("style") or "roman")


def _semantic_key(glyph: dict) -> tuple[str, str, tuple[tuple[int, int], ...]]:
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
    for group in raster_groups.values():
        if len(group) < 2:
            continue
        semantic = {(str(g.get("label") or ""), _typography(g)) for g in group}
        if len(semantic) < 2:
            continue
        ambiguities.append({
            "pixels": len(_pixels(group[0])),
            "models": sorted(group, key=_model_id_number),
        })

    duplicates.sort(key=lambda item: (item["label"], item["style"], _model_id_number(item["keep"])))
    ambiguities.sort(key=lambda item: (_model_id_number(item["models"][0]), item["pixels"]))

    return {
        "models": len(glyphs),
        "duplicate_groups": duplicates,
        "duplicate_models_removable": sum(len(item["remove"]) for item in duplicates),
        "raster_ambiguity_groups": ambiguities,
    }


def _model_text(glyph: dict) -> str:
    reviewed = "verified" if bool(glyph.get("reviewed", False)) else "UNVERIFIED"
    role = str(glyph.get("role") or "unknown")
    return f"{glyph.get('model_id')} {glyph.get('label')!r}/{_typography(glyph)} role={role} {reviewed} sources={len(glyph.get('sources') or [])}"


def render_report(report: dict) -> str:
    lines = [
        f"modeller: {report['models']}",
        f"verkliga duplikatgrupper: {len(report['duplicate_groups'])}",
        f"modeller som kan tas bort: {report['duplicate_models_removable']}",
        f"pixelidentiska men semantiskt olika grupper: {len(report['raster_ambiguity_groups'])}",
    ]

    if report["duplicate_groups"]:
        lines.append("\nVERKLIGA DUPLIKAT")
        for index, item in enumerate(report["duplicate_groups"], 1):
            lines.append(f"[{index}] {item['label']!r}/{item['style']} {item['pixels']} px")
            lines.append("  KEEP   " + _model_text(item["keep"]))
            for glyph in item["remove"]:
                lines.append("  REMOVE " + _model_text(glyph))

    if report["raster_ambiguity_groups"]:
        lines.append("\nPIXELIDENTISKA MEN SEMANTISKT OLIKA — RADERA INTE AUTOMATISKT")
        for index, item in enumerate(report["raster_ambiguity_groups"], 1):
            lines.append(f"[{index}] {item['pixels']} px")
            for glyph in item["models"]:
                lines.append("  " + _model_text(glyph))

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit exact duplicate and pixel-ambiguous glyph facit models")
    parser.add_argument("store", type=Path, nargs="?", default=Path("glyphs/facit-v2"))
    args = parser.parse_args(argv)
    payload = load_split_facit(args.store)
    print(render_report(audit_duplicates(payload)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
