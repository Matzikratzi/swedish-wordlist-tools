from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path


CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path("data/generated/ocr-page-cache/batch-defect-progress-v1.json")


def glyph_model_signature(model) -> str:
    payload = {
        "label": str(model.label),
        "style": str(model.style),
        "pixels": sorted((int(x), int(y)) for x, y in model.pixels),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def glyph_model_signature_set(models) -> set[str]:
    return {glyph_model_signature(model) for model in models}


class BatchProgressStore:
    """Persistent exact-prefix cache for interactive page batching.

    A cached prefix remains valid when the facit only grows: every model that
    existed when the prefix was proved exact must still exist now.  If a model
    was deleted, relabelled or repainted, the old prefix is discarded.

    We deliberately resume one physical row before the saved frontier.  That
    cheap one-row rewind protects against a row-boundary correction learned in
    the editor immediately after the batch scan stopped.
    """

    def __init__(self, path: Path = DEFAULT_CACHE_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": CACHE_VERSION, "pages": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": CACHE_VERSION, "pages": {}}
        if int(data.get("version", -1)) != CACHE_VERSION or not isinstance(data.get("pages"), dict):
            return {"version": CACHE_VERSION, "pages": {}}
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _key(page: int, threshold: int, source_digest: str) -> str:
        return f"p{int(page)}:t{int(threshold)}:{source_digest}"

    def resume_index(
        self,
        *,
        page: int,
        threshold: int,
        source_digest: str,
        row_count: int,
        models,
    ) -> tuple[int, bool]:
        key = self._key(page, threshold, source_digest)
        current_models = glyph_model_signature_set(models)
        with self._lock:
            record = self._data["pages"].get(key)
            if not record:
                return 0, False
            required = set(record.get("facit_models") or [])
            if not required.issubset(current_models):
                self._data["pages"].pop(key, None)
                self._save()
                return 0, False
            if int(record.get("row_count", -1)) != int(row_count):
                self._data["pages"].pop(key, None)
                self._save()
                return 0, False
            if bool(record.get("complete")):
                return row_count, True
            frontier = max(0, min(row_count, int(record.get("next_index", 0))))
            return max(0, frontier - 1), False

    def save_frontier(
        self,
        *,
        page: int,
        threshold: int,
        source_digest: str,
        row_count: int,
        next_index: int,
        models,
        complete: bool = False,
    ) -> None:
        key = self._key(page, threshold, source_digest)
        record = {
            "page": int(page),
            "threshold": int(threshold),
            "source_digest": str(source_digest),
            "row_count": int(row_count),
            "next_index": max(0, min(int(row_count), int(next_index))),
            "complete": bool(complete),
            "facit_models": sorted(glyph_model_signature_set(models)),
        }
        with self._lock:
            self._data["pages"][key] = record
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._data = {"version": CACHE_VERSION, "pages": {}}
            self._save()
