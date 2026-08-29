from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

V1_FORMAT = "saol14-manual-glyph-facit-v1"
V2_FORMAT = "saol14-manual-glyph-facit-v2"


def migrate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("format") == V2_FORMAT:
        return payload
    if payload.get("format") != V1_FORMAT:
        raise ValueError(f"unsupported facit format: {payload.get('format')!r}")

    glyphs = []
    for row in payload.get("glyphs") or []:
        migrated = dict(row)
        migrated["role"] = "unknown"
        migrated["legacy_style"] = str(row.get("style") or "roman")
        migrated.pop("style", None)
        glyphs.append(migrated)

    return {
        "format": V2_FORMAT,
        "coordinate_system": payload.get(
            "coordinate_system",
            "glyph x normalized to leftmost ink; y relative to support baseline",
        ),
        "policy": (
            "literal manually verified glyph rasters; semantic typography role is explicit; "
            "v1 style retained only as legacy provenance during migration"
        ),
        "roles": {
            "unknown": "verified raster, semantic typography role not yet re-verified",
            "headword-bold": "dictionary headword typography",
            "pos-roman": "part-of-speech marker typography",
            "inflection-italic": "inflection suffix/form typography",
            "context-italic": "context/example/reference italic typography",
            "definition-roman": "definition/explanatory roman typography",
            "inflection-label-roman": "small roman introductory/label text in inflection section",
        },
        "glyphs": glyphs,
    }


def migrate_file(source: Path, destination: Path) -> dict[str, Any]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    migrated = migrate_payload(payload)
    destination.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return migrated


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate SAOL manual glyph facit v1 to semantic-role facit v2.")
    ap.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit.json"),
    )
    ap.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit-v2.json"),
    )
    args = ap.parse_args()
    payload = migrate_file(args.source, args.destination)
    print(f"source={args.source}")
    print(f"destination={args.destination}")
    print(f"models={len(payload.get('glyphs') or [])}")
    print("roles=all migrated models start as unknown; legacy_style retained as provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
