from __future__ import annotations

"""Diagnostic wrapper around historical 81b9667 row discovery.

The wrapped scanner is left unchanged.  We duplicate only the homonym-seed
probe so the debug run can show whether any exact homonym model creates a seed,
which baselines survive a full-row walk, and whether the original scanner must
therefore fall back to its generic baseline search.
"""

from . import ocr_sequential_raw_page_rows as _scanner


_ORIGINAL_HOMONYM_SEED_WALKS = _scanner._homonym_seed_walks


def _homonym_seed_walks(raw, row_top, provisional_bottom, models, left, right):
    page_candidates = _scanner.cached._bound_page_candidates(models)
    probe_right = min(right, left + _scanner.HOMONYM_PROBE_WIDTH)
    candidate_rows = range(row_top, min(provisional_bottom, row_top + 12))
    seeds = []

    for anchor_y in candidate_rows:
        xs = sorted(x for x, y in raw if y == anchor_y and left <= x < probe_right)
        for anchor_x in xs:
            for model, min_x, left_pixels in page_candidates.homonym:
                x0 = anchor_x - min_x
                if x0 < left or x0 + model.width > probe_right:
                    continue
                for _mx, my in left_pixels:
                    baseline = anchor_y - my
                    if baseline < row_top or baseline >= provisional_bottom:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if placed and placed.issubset(raw):
                        seeds.append((anchor_x, anchor_y, baseline, model.label, len(placed), x0))

    unique = []
    seen = set()
    for item in seeds:
        key = (item[0], item[2], item[3], item[5])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    print(
        f"OLD81 HOMONYM: exact_seed_count={len(unique)} "
        f"row_top={row_top} probe_x={left}..{probe_right - 1}"
    )
    for anchor_x, anchor_y, baseline, label, pixels, x0 in unique[:40]:
        print(
            f"OLD81 HOMONYM SEED: label={label!r} anchor=({anchor_x},{anchor_y}) "
            f"x0={x0} derived_baseline={baseline} pixels={pixels}"
        )
    if len(unique) > 40:
        print(f"OLD81 HOMONYM SEED: ... {len(unique) - 40} more")

    walks = _ORIGINAL_HOMONYM_SEED_WALKS(
        raw, row_top, provisional_bottom, models, left, right
    )
    if walks:
        print("OLD81 HOMONYM: fallback=no")
        for (anchor_x, baseline), item in sorted(walks.items()):
            score, _ax, _baseline, _owned, glyphs, matched_right = item
            print(
                f"OLD81 HOMONYM WALK: anchor_x={anchor_x} baseline={baseline} "
                f"score={score} glyphs={glyphs} right={matched_right}"
            )
    else:
        print("OLD81 HOMONYM: fallback=yes (no verified homonym walk)")
    return walks


_scanner._homonym_seed_walks = _homonym_seed_walks

CachedRowBoundary = _scanner.CachedRowBoundary
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
