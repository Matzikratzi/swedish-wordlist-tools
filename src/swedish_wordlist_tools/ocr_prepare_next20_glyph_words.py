from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

ALPHABET = "abcdefghijklmnopqrstuvwxyzåäö"


def _manual_inventory(atlas: dict[str, object]) -> Counter[str]:
    c: Counter[str] = Counter()
    for word in atlas.get("words", []):
        if not isinstance(word, dict):
            continue
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            if str(ann.get("candidate_status") or "manual") != "manual":
                continue
            label = str(ann.get("label") or "")
            if label:
                c[label] += 1
    return c


def _seen_keys(atlas: dict[str, object]) -> set[tuple[str, str, str]]:
    out = set()
    for w in atlas.get("words", []):
        if not isinstance(w, dict):
            continue
        out.add((str(w.get("page") or ""), str(w.get("subnr") or ""), str(w.get("expected_word") or "")))
    return out


def _safe(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-zÅÄÖåäö_-]+", "_", s).strip("_")
    return s[:60] or "word"


def _load_page_image(meta: dict[str, object]) -> Image.Image | None:
    p = Path(str(meta.get("page_image") or ""))
    if p.exists():
        return Image.open(p).convert("L")
    src = str(meta.get("source") or "")
    if not src:
        return None
    try:
        with urllib.request.urlopen(src, timeout=30) as r, NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(r.read()); tmp.flush()
            return Image.open(tmp.name).convert("L")
    except Exception:
        return None


def _collect_candidates(manifest: dict[str, object], seen: set[tuple[str, str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, object, object, tuple[int, ...]], dict[str, object]] = {}
    for meta0 in (manifest.get("template_sources") or {}).values():
        if not isinstance(meta0, dict):
            continue
        bbox = meta0.get("page_word_bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        expected = str(meta0.get("expected_word") or meta0.get("source_word") or "")
        page = meta0.get("page")
        subnr = meta0.get("subnr")
        if not expected or (str(page or ""), str(subnr or ""), expected) in seen:
            continue
        key = (page, subnr, expected, tuple(int(x) for x in bbox))
        if key not in grouped:
            grouped[key] = dict(meta0)
    return list(grouped.values())


def _priority(meta: dict[str, object], inv: Counter[str]) -> tuple[float, int, str]:
    word = str(meta.get("expected_word") or meta.get("source_word") or "").lower()
    # Missing glyphs dominate, then scarce glyphs. Longer words are mildly useful
    # because one card can exercise more learned shapes.
    score = 0.0
    seen_chars = set(ch for ch in word if ch in ALPHABET)
    for ch in seen_chars:
        n = inv[ch]
        if n == 0:
            score += 100.0
        elif n < 3:
            score += 30.0 / n
        elif n < 6:
            score += 5.0 / n
    score += min(12, len(word)) * 0.05
    return (-score, int(meta.get("page") or 0), word)


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare a small batch of new faksimil words, prioritising missing/scarce learned glyphs.")
    ap.add_argument("atlas", type=Path)
    ap.add_argument("manifest", type=Path, help="Usually manifest-pages-bold-headwords.json")
    ap.add_argument("library", type=Path, help="Word-image library used by the pixel editor")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", type=Path, required=True, help="Output matches JSON for the pixel editor")
    args = ap.parse_args()

    atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    inv = _manual_inventory(atlas)
    seen = _seen_keys(atlas)
    candidates = _collect_candidates(manifest, seen)
    candidates.sort(key=lambda m: _priority(m, inv))

    count = max(1, args.count)
    selected = candidates[:count]
    words_dir = args.library / "words-next"
    words_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    failures: list[str] = []

    # Cache page images because several selected words can come from one page.
    page_cache: dict[str, Image.Image] = {}
    for i, meta in enumerate(selected):
        page_key = str(meta.get("page_image") or meta.get("source") or meta.get("page") or "")
        image = page_cache.get(page_key)
        if image is None:
            image = _load_page_image(meta)
            if image is None:
                failures.append(str(meta.get("expected_word") or "?"))
                continue
            page_cache[page_key] = image
        x, y, w, h = [int(v) for v in meta["page_word_bbox"]]
        x = max(0, x); y = max(0, y)
        w = max(1, min(w, image.width - x)); h = max(1, min(h, image.height - y))
        crop = image.crop((x, y, x + w, y + h))
        expected = str(meta.get("expected_word") or meta.get("source_word") or "")
        filename = f"n{i:02d}-p{int(meta.get('page') or 0)}-sub{meta.get('subnr')}-{_safe(expected)}.png"
        rel = f"words-next/{filename}"
        crop.save(args.library / rel)
        # Initial baseline is only a harmless fallback. v27/v28's ink-first
        # matches should vote a better baseline once learned glyphs are applied.
        baseline = max(0, h - 2)
        results.append({
            "source_id": f"next20:{i}:{meta.get('page')}:{meta.get('subnr')}",
            "style": str(meta.get("style") or "bold"),
            "expected_word": expected,
            "headword": expected,
            "page": meta.get("page"),
            "subnr": meta.get("subnr"),
            "word_file": rel,
            "width": w,
            "height": h,
            "baseline_y": baseline,
            "matches": {},
            "rejected_candidates": {},
        })

    payload = {
        "format": "saol-next-glyph-review-batch-v1",
        "source_atlas": str(args.atlas),
        "count_requested": count,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"available_new_words={len(candidates)} selected={len(results)} requested={count}")
    if failures:
        print("crop_failures=" + " ".join(failures))
    print("selected_words:")
    for r in results:
        word = str(r["expected_word"])
        interesting = "".join(sorted(set(ch for ch in word.lower() if ch in ALPHABET and inv[ch] < 3)))
        print(f"  p{r['page']} sub{r['subnr']} {word} scarce=[{interesting}]")
    print(f"matches={args.out}")
    return 0 if len(results) == count else 3


if __name__ == "__main__":
    raise SystemExit(main())
