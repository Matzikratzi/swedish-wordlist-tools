from __future__ import annotations

import argparse
import json
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


def _models(atlas: dict[str, object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for word in atlas.get("words", []):
        if not isinstance(word, dict):
            continue
        baseline = int(word.get("baseline_y") or 0)
        word_style = str(word.get("style") or "roman")
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            if str(ann.get("candidate_status") or "manual") != "manual":
                continue
            label = str(ann.get("label") or "")
            pixels0 = ann.get("pixels")
            if not label or label == "·" or not isinstance(pixels0, list) or not pixels0:
                continue
            pts = [(int(p[0]), int(p[1])) for p in pixels0 if isinstance(p, list) and len(p) == 2]
            if not pts:
                continue
            minx = min(x for x, _ in pts); maxx = max(x for x, _ in pts)
            miny = min(y for _, y in pts); maxy = max(y for _, y in pts)
            shape = sorted((x - minx, y - miny) for x, y in pts)
            out.append({
                "label": label,
                "style": str(ann.get("style") or word_style),
                "shape": shape,
                "width": maxx - minx + 1,
                "height": maxy - miny + 1,
                "baseline_offset": baseline - miny,
            })
    return out


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
        page = meta0.get("page"); subnr = meta0.get("subnr")
        if not expected or (str(page or ""), str(subnr or ""), expected) in seen:
            continue
        key = (page, subnr, expected, tuple(int(x) for x in bbox))
        grouped.setdefault(key, dict(meta0))
    return list(grouped.values())


def _priority(meta: dict[str, object], inv: Counter[str]) -> tuple[float, int, str]:
    word = str(meta.get("expected_word") or meta.get("source_word") or "").lower()
    score = 0.0
    for ch in set(ch for ch in word if ch in ALPHABET):
        n = inv[ch]
        if n == 0:
            score += 100.0
        elif n < 3:
            score += 30.0 / n
        elif n < 6:
            score += 5.0 / n
    score += min(12, len(word)) * 0.05
    return (-score, int(meta.get("page") or 0), word)


def _ink_mask(crop: Image.Image, threshold: int = 210) -> list[list[bool]]:
    im = crop.convert("L")
    return [[im.getpixel((x, y)) < threshold for x in range(im.width)] for y in range(im.height)]


def _match_models(crop: Image.Image, models: list[dict[str, object]]) -> tuple[dict[str, list[dict[str, object]]], int]:
    ink = _ink_mask(crop)
    H = len(ink); W = len(ink[0]) if H else 0
    by_key: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)

    # Every learned shape, regardless of style, competes against the source ink.
    for model in models:
        mw = int(model["width"]); mh = int(model["height"])
        if mw > W or mh > H:
            continue
        shape = list(model["shape"])
        total = len(shape)
        for y0 in range(0, H - mh + 1):
            for x0 in range(0, W - mw + 1):
                expected = {(x0 + dx, y0 + dy) for dx, dy in shape}
                matched_pts = [(x, y) for x, y in expected if ink[y][x]]
                matched = len(matched_pts)
                missing = total - matched
                if matched < 3 or missing / max(1, total) > 0.25:
                    continue
                extra = 0
                for yy in range(y0, y0 + mh):
                    for xx in range(x0, x0 + mw):
                        if ink[yy][xx] and (xx, yy) not in expected:
                            extra += 1
                if extra / max(1, total) > 0.35:
                    continue
                score = matched - 2 * missing - extra
                if score <= 0:
                    continue
                by_key[(str(model["label"]), str(model["style"]))].append({
                    "matched_pixels": [[x, y] for x, y in sorted(matched_pts)],
                    "external_contact_pixels": [],
                    "external_contacts": 0,
                    "missing": missing,
                    "extra": extra,
                    "score": score,
                    "style": str(model["style"]),
                    "baseline_hint": y0 + int(model["baseline_offset"]),
                })

    # Combine duplicate models and greedily keep strong non-overlapping placements
    # per label/style so repeated letters can still appear more than once.
    matches: dict[str, list[dict[str, object]]] = defaultdict(list)
    baseline_votes: Counter[int] = Counter()
    for (label, style), hits in by_key.items():
        uniq: dict[tuple[tuple[int, int], ...], dict[str, object]] = {}
        for hit in hits:
            key = tuple((int(x), int(y)) for x, y in hit["matched_pixels"])
            old = uniq.get(key)
            if old is None or float(hit["score"]) > float(old["score"]):
                uniq[key] = hit
        ordered = sorted(uniq.values(), key=lambda h: (-float(h["score"]), int(h["missing"]), int(h["extra"])))
        used: set[tuple[int, int]] = set()
        kept = 0
        for hit in ordered:
            pts = {(int(x), int(y)) for x, y in hit["matched_pixels"]}
            if pts & used:
                continue
            used |= pts
            matches[label].append(hit)
            baseline_votes[int(hit["baseline_hint"])] += 1
            kept += 1
            if kept >= 6:
                break
    baseline = baseline_votes.most_common(1)[0][0] if baseline_votes else max(0, H - 2)
    return dict(matches), baseline


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare 20 new faksimil words and pre-match all learned glyph styles against source ink.")
    ap.add_argument("atlas", type=Path)
    ap.add_argument("manifest", type=Path, help="Usually manifest-pages-bold-headwords.json")
    ap.add_argument("library", type=Path, help="Word-image library used by the pixel editor")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    inv = _manual_inventory(atlas)
    models = _models(atlas)
    seen = _seen_keys(atlas)
    candidates = _collect_candidates(manifest, seen)
    candidates.sort(key=lambda m: _priority(m, inv))

    count = max(1, args.count)
    selected = candidates[:count]
    (args.library / "words-next").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    page_cache: dict[str, Image.Image] = {}

    for i, meta in enumerate(selected):
        page_key = str(meta.get("page_image") or meta.get("source") or meta.get("page") or "")
        image = page_cache.get(page_key)
        if image is None:
            image = _load_page_image(meta)
            if image is None:
                failures.append(str(meta.get("expected_word") or "?")); continue
            page_cache[page_key] = image
        x, y, w, h = [int(v) for v in meta["page_word_bbox"]]
        x = max(0, x); y = max(0, y)
        w = max(1, min(w, image.width - x)); h = max(1, min(h, image.height - y))
        crop = image.crop((x, y, x + w, y + h))
        expected = str(meta.get("expected_word") or meta.get("source_word") or "")
        filename = f"n{i:02d}-p{int(meta.get('page') or 0)}-sub{meta.get('subnr')}-{_safe(expected)}.png"
        rel = f"words-next/{filename}"
        crop.save(args.library / rel)
        matches, baseline = _match_models(crop, models)
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
            "matches": matches,
            "rejected_candidates": {},
        })

    payload = {"format": "saol-next-glyph-review-batch-v2", "source_atlas": str(args.atlas), "count_requested": count, "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"models={len(models)} available_new_words={len(candidates)} selected={len(results)} requested={count}")
    if failures:
        print("crop_failures=" + " ".join(failures))
    print("selected_words:")
    for r in results:
        word = str(r["expected_word"])
        interesting = "".join(sorted(set(ch for ch in word.lower() if ch in ALPHABET and inv[ch] < 3)))
        found = sum(len(v) for v in r["matches"].values())
        print(f"  p{r['page']} sub{r['subnr']} {word} scarce=[{interesting}] prematches={found}")
    print(f"matches={args.out}")
    return 0 if len(results) == count else 3


if __name__ == "__main__":
    raise SystemExit(main())
