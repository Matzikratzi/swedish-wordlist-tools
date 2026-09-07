from __future__ import annotations

"""Observe and persist deterministic glyph-model popularity statistics."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from threading import local

from .ocr_glyph_matcher import GlyphModel

_tls = local()
PROFILE_FORMAT = "saol14-glyph-popularity-v1"


@dataclass(frozen=True)
class _ModelInfo:
    bucket: str
    rank: int
    bucket_size: int
    label: str
    typography: str
    sources: int
    stable_key: str


def reset_popularity_stats() -> None:
    _tls.hits = Counter()
    _tls.models = {}


def _stores() -> tuple[Counter[int], dict[int, _ModelInfo]]:
    hits = getattr(_tls, "hits", None)
    models = getattr(_tls, "models", None)
    if hits is None or models is None:
        reset_popularity_stats()
        hits = _tls.hits
        models = _tls.models
    return hits, models


def stable_model_key(model: GlyphModel, *, bucket: str, typography: str) -> str:
    """Stable identity across processes; independent of sources/review metadata."""
    raster = ";".join(f"{int(x)},{int(y)}" for x, y in sorted(model.pixels))
    return f"{bucket}|{typography}|{model.label}|{raster}"


def register_bucket(
    bucket: str,
    rows,
    *,
    typography_of,
) -> None:
    """Remember the current 1-based order of one immutable page bucket."""
    _hits, models = _stores()
    size = len(rows)
    for rank, row in enumerate(rows, start=1):
        model = row[0]
        typography = str(typography_of(model.style))
        key = id(model)
        models[key] = _ModelInfo(
            bucket=str(bucket),
            rank=rank,
            bucket_size=size,
            label=str(model.label),
            typography=typography,
            sources=int(model.sources),
            stable_key=stable_model_key(model, bucket=str(bucket), typography=typography),
        )


def record_model_hit(model: GlyphModel) -> None:
    hits, _models = _stores()
    hits[id(model)] += 1


def popularity_counts() -> dict[str, int]:
    """Return full stable model->hit counts from the current observation run."""
    hits, models = _stores()
    out: Counter[str] = Counter()
    for key, count in hits.items():
        info = models.get(key)
        if info is not None and count > 0:
            out[info.stable_key] += int(count)
    return dict(out)


def save_popularity_profile(path: Path) -> int:
    counts = popularity_counts()
    payload = {
        "format": PROFILE_FORMAT,
        "counts": dict(sorted(counts.items())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(counts)


def load_popularity_profile(path: Path | None) -> int:
    if path is None:
        _tls.profile = {}
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != PROFILE_FORMAT:
        raise ValueError(f"unsupported popularity profile format: {payload.get('format')!r}")
    raw = payload.get("counts") or {}
    _tls.profile = {str(key): int(value) for key, value in raw.items() if int(value) > 0}
    return len(_tls.profile)


def clear_popularity_profile() -> None:
    _tls.profile = {}


def popularity_weight(model: GlyphModel, *, bucket: str, typography: str) -> int:
    profile = getattr(_tls, "profile", None) or {}
    return int(profile.get(stable_model_key(model, bucket=bucket, typography=typography), 0))


def popularity_report(*, top_n: int = 12) -> list[dict]:
    """Return per-bucket rank statistics without modifying the model order."""
    hits, models = _stores()
    by_bucket: dict[str, list[tuple[int, _ModelInfo, int]]] = {}
    for key, count in hits.items():
        info = models.get(key)
        if info is None or count <= 0:
            continue
        by_bucket.setdefault(info.bucket, []).append((key, info, int(count)))

    out = []
    for bucket in ("homonym", "bold", "roman", "italic", "other"):
        rows = by_bucket.get(bucket) or []
        if not rows:
            continue
        total_hits = sum(count for _key, _info, count in rows)
        current_cost = sum(info.rank * count for _key, info, count in rows)
        popularity_order = sorted(rows, key=lambda row: (-row[2], row[1].rank))
        popularity_rank = {
            key: rank
            for rank, (key, _info, _count) in enumerate(popularity_order, start=1)
        }
        popularity_cost = sum(
            popularity_rank[key] * count for key, _info, count in rows
        )
        bucket_size = max(info.bucket_size for _key, info, _count in rows)
        top = [
            {
                "label": info.label,
                "typography": info.typography,
                "hits": count,
                "current_rank": info.rank,
                "popularity_rank": popularity_rank[key],
                "sources": info.sources,
            }
            for key, info, count in popularity_order[:top_n]
        ]
        out.append(
            {
                "bucket": bucket,
                "bucket_size": bucket_size,
                "distinct_hit_models": len(rows),
                "hits": total_hits,
                "current_avg_rank": current_cost / total_hits,
                "popularity_avg_rank": popularity_cost / total_hits,
                "rank_factor": (current_cost / popularity_cost) if popularity_cost else 1.0,
                "top": top,
            }
        )
    return out
