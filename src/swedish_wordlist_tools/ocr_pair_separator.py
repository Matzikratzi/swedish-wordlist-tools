from __future__ import annotations

"""Cheap bounded horizontal separator candidates for two adjacent OCR rows.

The helpers in this module know nothing about glyph matching.  They only inspect
page-wide byte ownership and propose/revert horizontal cuts.  A caller must
supply the exact proof policy and may commit a changed ownership assignment only
when both adjacent rows are proven exact.
"""


def distance_order(values: set[int], boundary: int) -> list[int]:
    """Try cuts nearest the current separator first; prefer deeper on ties."""
    return sorted(values, key=lambda y: (abs(int(y) - boundary), -int(y)))


def separator_window(boundary: int, radius: int, height: int) -> tuple[int, int]:
    return max(1, boundary - radius), min(height - 1, boundary + radius + 1)


def white_band_cuts(owners, *, boundary: int, left: int, right: int, radius: int) -> list[int]:
    lo, hi = separator_window(boundary, radius, owners.height)
    cuts: set[int] = set()
    for y in range(lo, hi + 1):
        # A separator lies between y-1 and y. If either adjacent raster line is
        # wholly white, no 8-connected component can cross this cut.
        if owners.horizontal_ink_count(y - 1, left=left, right=right) == 0:
            cuts.add(y)
        elif y < owners.height and owners.horizontal_ink_count(y, left=left, right=right) == 0:
            cuts.add(y)
    return distance_order(cuts, boundary)


def disconnected_cuts(owners, *, boundary: int, left: int, right: int, radius: int) -> list[int]:
    lo, hi = separator_window(boundary, radius, owners.height)
    cuts = {
        y
        for y in range(lo, hi + 1)
        if owners.boundary_bridge_count(y, left=left, right=right) == 0
    }
    return distance_order(cuts, boundary)


def owned_extrema_cuts(
    owners,
    *,
    upper_code: int,
    lower_code: int,
    boundary: int,
    left: int,
    right: int,
    radius: int,
) -> list[int]:
    """Suggest cuts around last upper-owned and first lower-owned ink lines."""
    lo, hi = separator_window(boundary, radius, owners.height)
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
    return distance_order(expanded, boundary)


def legacy_bounded_cuts(boundary: int, *, radius: int) -> list[int]:
    return list(range(boundary + radius, boundary - radius - 1, -1))


def candidate_separator_tiers(
    owners,
    *,
    upper_code: int,
    lower_code: int,
    boundary: int,
    left: int,
    right: int,
    radius: int,
) -> list[tuple[str, list[int]]]:
    """Return unique cuts in increasingly weak/expensive geometric tiers."""
    white = white_band_cuts(
        owners, boundary=boundary, left=left, right=right, radius=radius
    )
    disconnected = disconnected_cuts(
        owners, boundary=boundary, left=left, right=right, radius=radius
    )
    extrema = owned_extrema_cuts(
        owners,
        upper_code=upper_code,
        lower_code=lower_code,
        boundary=boundary,
        left=left,
        right=right,
        radius=radius,
    )
    legacy = legacy_bounded_cuts(boundary, radius=radius)

    seen: set[int] = set()
    tiers: list[tuple[str, list[int]]] = []
    for name, values in (
        ("white-band", white),
        ("8-disconnected", disconnected),
        ("owned-extrema", extrema),
        ("legacy-bounded", legacy),
    ):
        unique: list[int] = []
        for y in values:
            if y in seen:
                continue
            seen.add(y)
            unique.append(y)
        if unique:
            tiers.append((name, unique))
    return tiers


def apply_cut_bidirectional(
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
    """Reassign only the two adjacent row codes according to one cut."""
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


def restore_changed_ownership(owners, changed: list[tuple[int, int]]) -> None:
    for offset, old in reversed(changed):
        owners.data[offset] = old
