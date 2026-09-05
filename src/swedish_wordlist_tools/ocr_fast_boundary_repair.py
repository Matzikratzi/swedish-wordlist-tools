from __future__ import annotations

"""Bounded row-boundary repair for fast regression scans.

The cheap path is deliberately geometric before it is glyph-driven:

1. prefer a horizontal cut adjacent to a completely white raster line;
2. otherwise prefer a cut with no 8-connected ink bridge across it;
3. otherwise try cuts suggested by the current upper/lower ink extrema;
4. finally try the old bounded cuts around the geometric separator.

A candidate may move row-owned ink in *either* direction across the old
separator.  Nothing is committed unless the same fast-only exact analyser
proves both adjacent rows 100% exact.  No exhaustive glyph path is entered here.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_priority_fast_path import classify_row_start, set_row_priority_hint


@dataclass(frozen=True)
class FastBoundaryRepair:
    repaired: bool
    cut_y: int | None
    moved_pixels: int
    attempts: int
    elapsed: float
    strategy: str | None = None


def _column_span(context: dict, column: int) -> tuple[int, int]:
    owners = context["pixel_owners"]
    entry = context["row_map"]["columns"][column]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    return left, right


def _analyse_fast(context: dict, position: tuple[int, int], models) -> dict:
    set_row_priority_hint(classify_row_start(context, position))
    return page_editor._load_owned_row_state(context, position, models)


def _distance_order(values: set[int], boundary: int) -> list[int]:
    """Try cuts nearest the current separator first; prefer deeper on ties."""
    return sorted(values, key=lambda y: (abs(int(y) - boundary), -int(y)))


def _window(boundary: int, radius: int, height: int) -> tuple[int, int]:
    return max(1, boundary - radius), min(height - 1, boundary + radius + 1)


def _white_band_cuts(owners, *, boundary: int, left: int, right: int, radius: int) -> list[int]:
    lo, hi = _window(boundary, radius, owners.height)
    cuts: set[int] = set()
    for y in range(lo, hi + 1):
        # A separator lies between y-1 and y.  If either adjacent raster line is
        # wholly white in the lexical column span, no component can be cut.
        if owners.horizontal_ink_count(y - 1, left=left, right=right) == 0:
            cuts.add(y)
        elif y < owners.height and owners.horizontal_ink_count(y, left=left, right=right) == 0:
            cuts.add(y)
    return _distance_order(cuts, boundary)


def _disconnected_cuts(owners, *, boundary: int, left: int, right: int, radius: int) -> list[int]:
    lo, hi = _window(boundary, radius, owners.height)
    cuts = {
        y
        for y in range(lo, hi + 1)
        if owners.boundary_bridge_count(y, left=left, right=right) == 0
    }
    return _distance_order(cuts, boundary)


def _owned_extrema_cuts(
    owners,
    *,
    upper_code: int,
    lower_code: int,
    boundary: int,
    left: int,
    right: int,
    radius: int,
) -> list[int]:
    """Suggest cuts around the last upper-owned and first lower-owned ink lines."""
    lo, hi = _window(boundary, radius, owners.height)
    upper_ys: list[int] = []
    lower_ys: list[int] = []
    for y in range(lo - 1, min(owners.height, hi + 1)):
        start = y * owners.width
        row = owners.data[start + left : start + right]
        if upper_code in row:
            upper_ys.append(y)
        if lower_code in row:
            lower_ys.append(y)

    seeds: set[int] = set()
    if upper_ys:
        seeds.add(max(upper_ys) + 1)
    if lower_ys:
        seeds.add(min(lower_ys))

    expanded: set[int] = set()
    for seed in seeds:
        for delta in (-1, 0, 1):
            y = seed + delta
            if lo <= y <= hi:
                expanded.add(y)
    return _distance_order(expanded, boundary)


def _legacy_cuts(boundary: int, *, radius: int) -> list[int]:
    # Preserve the old deepest-to-shallowest fallback as the final bounded tier.
    return list(range(boundary + radius, boundary - radius - 1, -1))


def _candidate_tiers(
    context: dict,
    *,
    column: int,
    row_index: int,
    boundary: int,
    left: int,
    right: int,
    radius: int,
) -> list[tuple[str, list[int]]]:
    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)

    white = _white_band_cuts(
        owners, boundary=boundary, left=left, right=right, radius=radius
    )
    disconnected = _disconnected_cuts(
        owners, boundary=boundary, left=left, right=right, radius=radius
    )
    extrema = _owned_extrema_cuts(
        owners,
        upper_code=upper_code,
        lower_code=lower_code,
        boundary=boundary,
        left=left,
        right=right,
        radius=radius,
    )
    legacy = _legacy_cuts(boundary, radius=radius)

    # Do not pay for the same exact proof twice just because a cut qualifies for
    # several increasingly weak heuristics.
    seen: set[int] = set()
    tiers: list[tuple[str, list[int]]] = []
    for name, values in (
        ("white-band", white),
        ("8-disconnected", disconnected),
        ("owned-extrema", extrema),
        ("legacy-bounded", legacy),
    ):
        unique = [y for y in values if not (y in seen or seen.add(y))]
        if unique:
            tiers.append((name, unique))
    return tiers


def _apply_cut_bidirectional(
    owners,
    *,
    upper_code: int,
    lower_code: int,
    cut_y: int,
    boundary: int,
    left: int,
    right: int,
    radius: int,
) -> list[tuple[int, int]]:
    """Reassign only the two adjacent row codes according to one candidate cut."""
    y0 = max(0, boundary - radius - 1)
    y1 = min(owners.height, boundary + radius + 2)
    changed: list[tuple[int, int]] = []
    for y in range(y0, y1):
        wanted = upper_code if y < cut_y else lower_code
        start = y * owners.width
        for x in range(left, right):
            offset = start + x
            old = owners.data[offset]
            if old not in (upper_code, lower_code) or old == wanted:
                continue
            owners.data[offset] = wanted
            changed.append((offset, old))
    return changed


def try_fast_boundary_repair(
    context: dict,
    position: tuple[int, int],
    models,
    *,
    radius: int = 6,
) -> FastBoundaryRepair:
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []
    if row_index + 1 >= len(rows):
        return FastBoundaryRepair(False, None, 0, 0, 0.0, None)

    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    lower_position = (column, row_index + 1)
    boundary = int(rows[row_index]["page_bottom"])
    left, right = _column_span(context, column)
    started = perf_counter()
    attempts = 0

    for strategy, cuts in _candidate_tiers(
        context,
        column=column,
        row_index=row_index,
        boundary=boundary,
        left=left,
        right=right,
        radius=radius,
    ):
        for cut_y in cuts:
            changed = _apply_cut_bidirectional(
                owners,
                upper_code=upper_code,
                lower_code=lower_code,
                cut_y=cut_y,
                boundary=boundary,
                left=left,
                right=right,
                radius=radius,
            )
            if not changed:
                continue

            attempts += 1
            upper = _analyse_fast(context, position, models)
            if upper.get("fully_exact"):
                lower = _analyse_fast(context, lower_position, models)
                if lower.get("fully_exact"):
                    return FastBoundaryRepair(
                        True,
                        cut_y,
                        len(changed),
                        attempts,
                        perf_counter() - started,
                        strategy,
                    )

            for offset, old in reversed(changed):
                owners.data[offset] = old

    return FastBoundaryRepair(False, None, 0, attempts, perf_counter() - started, None)
