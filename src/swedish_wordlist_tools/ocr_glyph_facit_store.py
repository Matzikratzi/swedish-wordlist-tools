from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

FACIT_V2 = "saol14-manual-glyph-facit-v2"
META_FILE = "_meta.json"
MODEL_ID_PREFIX = "g"
CANONICAL_AGGREGATE_NAME = "saol14-manual-glyph-facit-v2.json"
CANONICAL_STORE_NAME = "facit-v2"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    """Write JSON without Path.write_text so editor write redirection cannot recurse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _validate_v2(payload: dict) -> None:
    if payload.get("format") != FACIT_V2:
        raise ValueError(f"expected {FACIT_V2!r}, got {payload.get('format')!r}")
    if not isinstance(payload.get("glyphs"), list):
        raise ValueError("facit payload must contain a glyphs list")


def label_directory(label: str) -> str:
    """Return a filesystem-safe, deterministic directory name for one glyph label."""
    if not label:
        return "empty"
    return "-".join(f"u{ord(char):04x}" for char in label)


def canonical_store_for_facit(facit_path: Path) -> Path | None:
    """Return the canonical split-store path for the project's v2 aggregate."""
    facit_path = Path(facit_path)
    if facit_path.name != CANONICAL_AGGREGATE_NAME:
        return None
    return facit_path.parent / CANONICAL_STORE_NAME


def _parse_model_id(value: object) -> int | None:
    text = str(value or "")
    if not text.startswith(MODEL_ID_PREFIX):
        return None
    digits = text[len(MODEL_ID_PREFIX):]
    if not digits.isdigit():
        return None
    return int(digits)


def ensure_model_ids(payload: dict) -> int:
    """Assign stable one-time ids to v2 glyph models that do not already have one."""
    _validate_v2(payload)
    used: set[int] = set()
    for glyph in payload["glyphs"]:
        number = _parse_model_id(glyph.get("model_id"))
        if number is None:
            continue
        if number in used:
            raise ValueError(f"duplicate model_id: {glyph['model_id']!r}")
        used.add(number)

    next_id = max(used, default=0) + 1
    changed = 0
    for glyph in payload["glyphs"]:
        if _parse_model_id(glyph.get("model_id")) is not None:
            continue
        while next_id in used:
            next_id += 1
        glyph["model_id"] = f"{MODEL_ID_PREFIX}{next_id:06d}"
        used.add(next_id)
        next_id += 1
        changed += 1
    return changed


def write_split_facit(payload: dict, store_dir: Path) -> tuple[int, int]:
    """Persist one canonical JSON file per model and remove stale/moved files."""
    _validate_v2(payload)
    assigned = ensure_model_ids(payload)
    store_dir = Path(store_dir)

    meta = {key: value for key, value in payload.items() if key != "glyphs"}
    _write_json(store_dir / META_FILE, meta)

    desired: set[Path] = {store_dir / META_FILE}
    for glyph in payload["glyphs"]:
        model_id = str(glyph["model_id"])
        path = store_dir / label_directory(str(glyph.get("label") or "")) / f"{model_id}.json"
        _write_json(path, glyph)
        desired.add(path)

    if store_dir.exists():
        for path in sorted(store_dir.rglob("*.json")):
            if path not in desired:
                path.unlink()
        for directory in sorted((p for p in store_dir.rglob("*") if p.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    return len(payload["glyphs"]), assigned


def persist_facit_payload(facit_path: Path, payload: dict, *, store_dir: Path | None = None) -> tuple[int, int]:
    """Write split store first, then regenerate the compatibility aggregate.

    This is the canonical editor persistence path. The per-model store is the
    durable source; the historical aggregate remains available to existing
    readers and command lines, but is rebuilt from the just-written split store.
    """
    facit_path = Path(facit_path)
    if store_dir is None:
        store_dir = canonical_store_for_facit(facit_path)
    if store_dir is None:
        raise ValueError(f"no canonical split store configured for {facit_path}")
    count, assigned = write_split_facit(payload, store_dir)
    rebuilt = load_split_facit(store_dir)
    _write_json(facit_path, rebuilt)
    return count, assigned


def split_facit(facit_path: Path, store_dir: Path, *, write_ids: bool = True) -> tuple[int, int]:
    """Materialize one JSON file per glyph model while keeping the aggregate facit compatible."""
    payload = _read_json(facit_path)
    _validate_v2(payload)
    count, assigned = write_split_facit(payload, store_dir)
    if write_ids and assigned:
        _write_json(facit_path, payload)
    return count, assigned


def load_split_facit(store_dir: Path) -> dict:
    meta_path = store_dir / META_FILE
    if not meta_path.exists():
        raise ValueError(f"missing split facit metadata: {meta_path}")
    payload = _read_json(meta_path)
    if "glyphs" in payload:
        raise ValueError(f"{META_FILE} must not contain glyphs")

    models: list[tuple[int, dict]] = []
    seen: set[int] = set()
    for path in sorted(store_dir.rglob(f"{MODEL_ID_PREFIX}*.json")):
        if path.name == META_FILE:
            continue
        glyph = _read_json(path)
        number = _parse_model_id(glyph.get("model_id"))
        if number is None:
            raise ValueError(f"invalid model_id in {path}")
        if number in seen:
            raise ValueError(f"duplicate model_id g{number:06d} in split facit")
        seen.add(number)
        expected_dir = label_directory(str(glyph.get("label") or ""))
        if path.parent.name != expected_dir:
            raise ValueError(f"glyph {glyph['model_id']} is stored under {path.parent.name!r}, expected {expected_dir!r}")
        models.append((number, glyph))

    models.sort(key=lambda pair: pair[0])
    payload["glyphs"] = [glyph for _number, glyph in models]
    _validate_v2(payload)
    return payload


def build_facit(store_dir: Path, output_path: Path) -> int:
    payload = load_split_facit(store_dir)
    _write_json(output_path, payload)
    return len(payload["glyphs"])


def verify_facit(facit_path: Path, store_dir: Path) -> tuple[bool, str]:
    aggregate = _read_json(facit_path)
    split = load_split_facit(store_dir)
    if aggregate == split:
        return True, f"OK: {len(split['glyphs'])} modeller; split facit == aggregate"
    return False, "FEL: split facit och aggregate skiljer sig"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Split/build SAOL14 glyph facit v2 as one JSON file per model")
    sub = parser.add_subparsers(dest="command", required=True)

    split = sub.add_parser("split", help="split aggregate v2 facit into one file per model")
    split.add_argument("facit", type=Path)
    split.add_argument("store", type=Path)
    split.add_argument("--no-write-ids", action="store_true", help="do not persist newly assigned model_id fields back to aggregate")

    build = sub.add_parser("build", help="build aggregate v2 facit from split store")
    build.add_argument("store", type=Path)
    build.add_argument("output", type=Path)

    verify = sub.add_parser("verify", help="verify that aggregate and split store are exactly equal")
    verify.add_argument("facit", type=Path)
    verify.add_argument("store", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "split":
        count, assigned = split_facit(args.facit, args.store, write_ids=not args.no_write_ids)
        print(f"split: {count} modeller, {assigned} nya model_id -> {args.store}")
        return 0
    if args.command == "build":
        count = build_facit(args.store, args.output)
        print(f"build: {count} modeller -> {args.output}")
        return 0
    ok, message = verify_facit(args.facit, args.store)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
