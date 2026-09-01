from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Callable

CACHE_FORMAT = "saol14-pixel-page-cache-v1"
DEFAULT_CACHE_DIR = Path("data/generated/ocr-page-cache")


def _hash_bytes(*chunks: bytes) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(len(chunk).to_bytes(8, "big"))
        digest.update(chunk)
    return digest.hexdigest()


def _module_bytes(module_file: str) -> bytes:
    return Path(module_file).read_bytes()


def page_image_fingerprint(page) -> str:
    """Fingerprint the already-loaded source raster without reopening the image."""
    return _hash_bytes(
        str(page.mode).encode("utf-8"),
        f"{page.width}x{page.height}".encode("ascii"),
        page.tobytes(),
    )


def geometry_cache_key(page, *, threshold: int, segmentation_module_file: str) -> str:
    return _hash_bytes(
        CACHE_FORMAT.encode("ascii"),
        b"geometry",
        page_image_fingerprint(page).encode("ascii"),
        str(threshold).encode("ascii"),
        _module_bytes(segmentation_module_file),
    )


def glyph_cache_key(
    geometry_key: str,
    facit: Path,
    *,
    matcher_module_file: str,
    row_probe_module_file: str,
    row_map_module_file: str,
    extra_module_files: tuple[str, ...] = (),
) -> str:
    return _hash_bytes(
        CACHE_FORMAT.encode("ascii"),
        b"glyphs",
        geometry_key.encode("ascii"),
        facit.read_bytes(),
        _module_bytes(matcher_module_file),
        _module_bytes(row_probe_module_file),
        _module_bytes(row_map_module_file),
        *(_module_bytes(module_file) for module_file in extra_module_files),
    )


def _path(cache_dir: Path, page_number: int, kind: str, key: str) -> Path:
    return cache_dir / f"page-{page_number:04d}-{kind}-{key[:20]}.pickle"


def load_or_compute(
    cache_dir: Path,
    page_number: int,
    kind: str,
    key: str,
    compute: Callable[[], object],
) -> tuple[object, bool, Path]:
    """Return cached value or compute and atomically save it.

    The boolean is True for a cache hit and False when ``compute`` was called.
    Cache files are disposable generated data; corrupt entries are ignored and
    rebuilt rather than making the OCR run fail.
    """
    path = _path(cache_dir, page_number, kind, key)
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        if payload.get("format") == CACHE_FORMAT and payload.get("key") == key:
            return payload["value"], True, path
    except (OSError, EOFError, pickle.PickleError, AttributeError, TypeError, ValueError):
        pass

    value = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        pickle.dump({"format": CACHE_FORMAT, "key": key, "value": value}, handle, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    return value, False, path
