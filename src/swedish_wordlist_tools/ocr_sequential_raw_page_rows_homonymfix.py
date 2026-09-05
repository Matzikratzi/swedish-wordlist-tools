from __future__ import annotations

"""Hybrid correctness probe for the sequential raw-page scanner.

This wrapper deliberately leaves the main scanner untouched while restoring two
principles from historical commit 81b9667:

* an exact homonym glyph at the left edge may propose the row baseline;
* competing baseline hypotheses are verified by walking the whole row, with
  explained horizontal span ranked before glyph/pixel count.

Unlike the previous diagnostic wrapper there is no hard-coded vertical crop and
no x +/- 1 homonym placement heuristic.  The point of this experiment is to
separate baseline-search correctness from facit correctness.
"""

from . import ocr_sequential_raw_page_rows as _scanner


_ORIGINAL_PAGE1_BASELINE_PROBE_WALKS = _scanner._page1_baseline_probe_walks


def _homonym_baseline_seeds(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
) -> dict[int, set[tuple[int, int]]]:
    """Return exact homonym-derived baseline candidates and their proved pixels."""
    page_candidates = _scanner.cached._bound_page_candidates(models)
    probe_right = min(right, left + _scanner.HOMONYM_PROBE_WIDTH)
    anchor_bottom = min(search_limit, search_from + _scanner.START_SEARCH_HEIGHT)
    seeds: dict[int, set[tuple[int, int]]] = {}

    for anchor_y in range(search_from, anchor_bottom):
        xs = sorted(x for x, y in raw if y == anchor_y and left <= x < probe_right)
        for anchor_x in xs:
            for model, min_x, left_pixels in page_candidates.homonym:
                x0 = anchor_x - min_x
                if x0 < left or x0 + model.width > probe_right:
                    continue
                for _mx, my in left_pixels:
                    baseline = anchor_y - my
                    if baseline < search_from or baseline >= search_limit:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if not placed or not placed.issubset(raw):
                        continue
                    old = seeds.get(baseline)
                    if old is None or len(placed) > len(old):
                        seeds[baseline] = placed

    return seeds


def _page1_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    """Let an exact homonym seed the baseline, then verify ordinary headword text."""
    page_candidates = _scanner.cached._bound_page_candidates(models)
    first_candidates = tuple(
        _scanner._bold_candidates(page_candidates, _scanner.PAGE1_EXACT_LABELS)
    )
    seeds = _homonym_baseline_seeds(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
    )

    walks = {}
    for baseline, homonym_owned in sorted(seeds.items()):
        exact_first = _scanner._exact_first_candidates(
            raw,
            baseline,
            first_candidates,
            first_ink_x,
            left,
            right,
        )
        if not exact_first:
            continue
        glyphs, owned, matched_right = _scanner._walk_baseline(
            raw,
            baseline,
            models,
            left,
            right,
            first_ink_x,
            first_candidates=exact_first,
        )
        if glyphs <= 0 or not owned:
            continue
        total_owned = set(owned)
        total_owned.update(homonym_owned)
        score = (matched_right - first_ink_x, glyphs + 1, len(total_owned))
        walks[(first_ink_x, baseline)] = (
            score,
            None,
            first_ink_x,
            total_owned,
            glyphs + 1,
            matched_right,
        )

    if walks:
        baselines = ",".join(str(b) for _x, b in sorted(walks))
        print(f"raw-page-homonym-baseline-seed: baselines={baselines}")
        return walks

    print("raw-page-homonym-baseline-seed: no exact seed; using ordinary page1 probe")
    return _ORIGINAL_PAGE1_BASELINE_PROBE_WALKS(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
        first_ink_x,
    )


def _ordinary_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
    first_candidates,
):
    """Verify every baseline hypothesis with a full row walk.

    This keeps the current x-first anchor and current border geometry.  Only the
    choice between baseline hypotheses changes: a candidate must compete on the
    amount of the real row it can explain instead of being judged after only
    three glyphs.
    """
    hypotheses: set[int] = set()
    anchor_bottom = min(search_limit, search_from + _scanner.START_SEARCH_HEIGHT)
    for anchor_y in range(search_from, anchor_bottom):
        if (anchor_x, anchor_y) not in raw:
            continue
        for model, min_x, left_pixels in first_candidates:
            x0 = anchor_x - min_x
            if x0 < left or x0 + model.width > right:
                continue
            for _mx, my in left_pixels:
                baseline = anchor_y - my
                if baseline < search_from or baseline >= search_limit:
                    continue
                placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                if placed and placed.issubset(raw):
                    hypotheses.add(baseline)

    walks = {}
    for baseline in sorted(hypotheses):
        exact_first = _scanner._exact_first_candidates(
            raw,
            baseline,
            first_candidates,
            anchor_x,
            left,
            right,
        )
        if not exact_first:
            continue
        glyphs, owned, matched_right = _scanner._walk_baseline(
            raw,
            baseline,
            models,
            left,
            right,
            anchor_x,
            first_candidates=exact_first,
        )
        if glyphs <= 0 or not owned:
            continue
        score = (matched_right - anchor_x, glyphs, len(owned))
        walks[(anchor_x, baseline)] = (
            score,
            None,
            anchor_x,
            owned,
            glyphs,
            matched_right,
        )

    if walks:
        diagnostics = ", ".join(
            f"b={baseline}:score={item[0]}"
            for (_x, baseline), item in sorted(walks.items())
        )
        print(f"raw-page-full-row-baseline-candidates: {diagnostics}")
    return walks


_scanner._page1_baseline_probe_walks = _page1_baseline_probe_walks
_scanner._ordinary_baseline_probe_walks = _ordinary_baseline_probe_walks

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
