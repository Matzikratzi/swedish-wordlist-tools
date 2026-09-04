from __future__ import annotations

"""Measure which prepared glyph candidates actually win exact-cover searches.

This is deliberately observational: it never changes candidate ordering.  The
batch scanner can therefore collect a few pages first and show how much a later
popularity ordering could reduce the average position of successful candidates.
"""

from collections import Counter
from dataclasses import dataclass
from threading import local

from .ocr_glyph_matcher import GlyphModel

_tls = local()


@dataclass(frozen=True)
class _ModelInfo:
    bucket: str
    rank: int
    bucket_size: int
    label: str
    typography: str
    sources: int


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
        key = id(model)
        models[key] = _ModelInfo(
            bucket=str(bucket),
            rank=rank,
            bucket_size=size,
            label=str(model.label),
            typography=str(typography_of(model.style)),
            sources=int(model.sources),
        )


def record_model_hit(model: GlyphModel) -> None:
    hits, _models = _stores()
    hits[id(model)] += 1


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
        popularity_rank = {key: rank for rank, (key, _info, _count) in enumerate(popularity_order, start=1)}
        popularity_cost = sum(popularity_rank[key] * count for key, _info, count in rows)
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
