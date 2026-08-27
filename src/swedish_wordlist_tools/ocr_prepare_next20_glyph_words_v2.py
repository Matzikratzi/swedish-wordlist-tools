from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import ocr_prepare_next20_glyph_words as v1


def _key(page: object, subnr: object, word: object) -> tuple[str, str, str]:
    return (str(page or ""), str(subnr or ""), str(word or ""))


def _load_seen_file(path: Path | None) -> set[tuple[str, str, str]]:
    if path is None or not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("seen") if isinstance(payload, dict) else payload
    out: set[tuple[str, str, str]] = set()
    for row in rows or []:
        if isinstance(row, dict):
            out.add(_key(row.get("page"), row.get("subnr"), row.get("expected_word")))
        elif isinstance(row, list) and len(row) >= 3:
            out.add(_key(row[0], row[1], row[2]))
    return out


def _load_batch_keys(path: Path) -> set[tuple[str, str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results") or payload.get("words") or []
    out: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.add(_key(row.get("page"), row.get("subnr"), row.get("expected_word") or row.get("headword")))
    return out


def _write_seen_file(path: Path, seen: set[tuple[str, str, str]]) -> None:
    rows = [
        {"page": page, "subnr": subnr, "expected_word": word}
        for page, subnr, word in sorted(seen, key=lambda r: (int(r[0]) if r[0].isdigit() else 0, r[1], r[2]))
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"format": "saol-glyph-batch-seen-v1", "seen": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _facit_inventory(path: Path | None) -> Counter[tuple[str, str]]:
    out: Counter[tuple[str, str]] = Counter()
    if path is None or not path.exists():
        return out
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("glyphs") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").lower()
        style = str(row.get("style") or "roman")
        if label:
            out[(label, style)] += 1
    return out


def _word_mix(meta: dict[str, object], facit_inv: Counter[tuple[str, str]]) -> tuple[set[str], set[str], str]:
    word = str(meta.get("expected_word") or meta.get("source_word") or "").lower()
    style = str(meta.get("style") or "bold")
    chars = {ch for ch in word if ch in v1.ALPHABET}
    known = {ch for ch in chars if facit_inv[(ch, style)] > 0}
    new = chars - known
    return known, new, style


def _mixed_priority(meta: dict[str, object], facit_inv: Counter[tuple[str, str]]) -> tuple[float, int, int, int, str]:
    """Prefer words mixing known and unseen label/style glyphs.

    First priority is at least one already learned and at least one unseen
    character in the word's source style. Within that class, prefer more unseen
    characters but retain several known anchors. If no unseen character remains,
    prefer label/style pairs with few learned raster variants.
    """
    word = str(meta.get("expected_word") or meta.get("source_word") or "").lower()
    known, new, style = _word_mix(meta, facit_inv)
    mixed = bool(known and new)
    scarcity = 0.0
    for ch in {c for c in word if c in v1.ALPHABET}:
        n = facit_inv[(ch, style)]
        scarcity += 20.0 if n == 0 else 4.0 / n
    # Lower tuple sorts first. Mixed words dominate; then maximize new glyphs,
    # then known anchors, then scarcity/length for useful context.
    return (
        0.0 if mixed else 1.0,
        -len(new),
        -len(known),
        -int(round(scarcity * 100)),
        word,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prepare a new glyph-review batch while persistently excluding shown words and optionally prioritizing mixed known/new glyphs."
    )
    ap.add_argument("atlas", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--seen-file",
        type=Path,
        default=Path("glyphs/saol14-glyph-batch-seen.json"),
        help="Persistent reviewed-word journal; defaults inside the repository.",
    )
    ap.add_argument(
        "--exclude-batch",
        type=Path,
        action="append",
        default=[],
        help="Existing batch JSON to import into the persistent seen journal; may be repeated.",
    )
    ap.add_argument(
        "--facit",
        type=Path,
        help="Current glyph facit; with --mixed-known-new, prioritize words containing both learned and unseen label/style glyphs.",
    )
    ap.add_argument("--mixed-known-new", action="store_true")
    args = ap.parse_args()

    atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    inv = v1._manual_inventory(atlas)
    models = v1._models(atlas)

    seen = v1._seen_keys(atlas)
    persistent_seen = _load_seen_file(args.seen_file)
    seen.update(persistent_seen)
    imported = 0
    for batch in args.exclude_batch:
        keys = _load_batch_keys(batch)
        imported += len(keys - seen)
        seen.update(keys)

    candidates = v1._collect_candidates(manifest, seen)
    facit_inv = _facit_inventory(args.facit)
    if args.mixed_known_new:
        if not facit_inv:
            raise SystemExit("--mixed-known-new requires a readable non-empty --facit")
        candidates.sort(key=lambda m: (_mixed_priority(m, facit_inv), int(m.get("page") or 0)))
    else:
        candidates.sort(key=lambda m: v1._priority(m, inv))
    count = max(1, args.count)
    selected = candidates[:count]

    (args.library / "words-next").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    page_cache = {}

    for i, meta in enumerate(selected):
        page_key = str(meta.get("page_image") or meta.get("source") or meta.get("page") or "")
        image = page_cache.get(page_key)
        if image is None:
            image = v1._load_page_image(meta)
            if image is None:
                failures.append(str(meta.get("expected_word") or "?"))
                continue
            page_cache[page_key] = image

        x, y, w, h = [int(v) for v in meta["page_word_bbox"]]
        x = max(0, x)
        y = max(0, y)
        w = max(1, min(w, image.width - x))
        h = max(1, min(h, image.height - y))
        crop = image.crop((x, y, x + w, y + h))
        expected = str(meta.get("expected_word") or meta.get("source_word") or "")
        filename = f"n{i:02d}-p{int(meta.get('page') or 0)}-sub{meta.get('subnr')}-{v1._safe(expected)}.png"
        rel = f"words-next/{filename}"
        crop.save(args.library / rel)
        matches, baseline = v1._match_models(crop, models)
        results.append(
            {
                "source_id": f"next20v2:{i}:{meta.get('page')}:{meta.get('subnr')}",
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
            }
        )

    payload = {
        "format": "saol-next-glyph-review-batch-v2",
        "source_atlas": str(args.atlas),
        "count_requested": count,
        "selection": "mixed-known-new" if args.mixed_known_new else "legacy-priority",
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for row in results:
        seen.add(_key(row.get("page"), row.get("subnr"), row.get("expected_word")))
    _write_seen_file(args.seen_file, seen)

    print(
        f"atlas_seen={len(v1._seen_keys(atlas))} persistent_seen_before={len(persistent_seen)} "
        f"imported={imported} available_new_words={len(candidates)} selected={len(results)} requested={count}"
    )
    if failures:
        print("crop_failures=" + " ".join(failures))
    print("selected_words:")
    for row in results:
        meta = next((m for m in selected if str(m.get("page")) == str(row.get("page")) and str(m.get("subnr")) == str(row.get("subnr")) and str(m.get("expected_word") or m.get("source_word") or "") == str(row.get("expected_word") or "")), {})
        if args.mixed_known_new:
            known, new, style = _word_mix(meta, facit_inv)
            print(f"  p{row['page']} sub{row['subnr']} {row['expected_word']} style={style} old=[{''.join(sorted(known))}] new=[{''.join(sorted(new))}]")
        else:
            print(f"  p{row['page']} sub{row['subnr']} {row['expected_word']}")
    print(f"seen_file={args.seen_file}")
    print(f"batch={args.out}")
    return 0 if len(results) == count else 3


if __name__ == "__main__":
    raise SystemExit(main())
