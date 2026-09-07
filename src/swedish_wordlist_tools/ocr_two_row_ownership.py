from __future__ import annotations

from collections import deque
from typing import Any, Callable


def _components(points: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
    result: list[set[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    point = (nx, ny)
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        queue.append(point)
        result.append(component)
    return result


def _reachable_within(
    allowed: set[tuple[int, int]],
    seeds: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    seen = set(seeds) & allowed
    queue = deque(seen)
    while queue:
        x, y = queue.popleft()
        for ny in range(y - 1, y + 2):
            for nx in range(x - 1, x + 2):
                point = (nx, ny)
                if point in allowed and point not in seen:
                    seen.add(point)
                    queue.append(point)
    return seen


def _contact_edges(
    target: set[tuple[int, int]],
    neighbor: set[tuple[int, int]],
) -> set[tuple[tuple[int, int], tuple[int, int]]]:
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for x, y in neighbor:
        for ny in range(y - 1, y + 2):
            for nx in range(x - 1, x + 2):
                other = (nx, ny)
                if other in target:
                    edges.add((other, (x, y)))
    return edges


def _foreign_edge_pixels(
    component: set[tuple[int, int]],
    *,
    crop_top: int,
    crop_bottom: int,
    core_top: int,
    core_bottom: int,
    neighbor_core_top: int | None,
    neighbor_core_bottom: int | None,
    side: str,
    max_contact_edges: int = 2,
) -> set[tuple[int, int]]:
    """Find crop-edge pixels owned by an adjacent physical row.

    Coordinates are in the wider probe-region coordinate system.  We only
    split when the candidate component is anchored in both physical row cores
    and the two sides meet through at most ``max_contact_edges`` 8-neighbour
    edges.  Only pixels outside the target core are removed; target-core pixels
    are never guessed away.
    """
    target_core = {
        point for point in component if core_top <= point[1] < core_bottom
    }
    if len(target_core) < 3:
        return set()

    if side == "below":
        if neighbor_core_top is None or neighbor_core_bottom is None:
            return set()
        neighbor_anchor = {
            point
            for point in component
            if neighbor_core_top <= point[1] < neighbor_core_bottom
        }
        allowed = {point for point in component if point[1] >= core_bottom}
        seeds = neighbor_anchor & allowed
        foreign_in_crop = lambda p: crop_top <= p[1] < crop_bottom and p[1] >= core_bottom
    elif side == "above":
        if neighbor_core_top is None or neighbor_core_bottom is None:
            return set()
        neighbor_anchor = {
            point
            for point in component
            if neighbor_core_top <= point[1] < neighbor_core_bottom
        }
        allowed = {point for point in component if point[1] < core_top}
        seeds = neighbor_anchor & allowed
        foreign_in_crop = lambda p: crop_top <= p[1] < crop_bottom and p[1] < core_top
    else:
        raise ValueError(f"unknown side: {side}")

    # A few pixels merely protruding toward the neighbouring row are not enough
    # evidence.  Require a real anchor in that row's own physical core.
    if len(neighbor_anchor) < 3 or not seeds:
        return set()

    neighbor_side = _reachable_within(allowed, seeds)
    removable = {point for point in neighbor_side if foreign_in_crop(point)}
    if not removable:
        return set()

    contacts = _contact_edges(target_core, neighbor_side)
    if not 1 <= len(contacts) <= max_contact_edges:
        return set()

    # The contact must also be spatially narrow. Two diagonal/orthogonal edges
    # at the same tiny touch are fine; a broad join is deliberately left alone.
    contact_x = {neighbor_point[0] for _target_point, neighbor_point in contacts}
    if max(contact_x) - min(contact_x) > 1:
        return set()

    return removable


def owned_row_crop_with_two_row_split(
    base_owned_row_crop: Callable,
    page_image,
    row: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    neighbor_above: dict[str, Any] | None = None,
    neighbor_below: dict[str, Any] | None = None,
    threshold: int = 210,
    probe_y: int = 8,
) -> tuple[Any, int]:
    """Conservatively separate accidental contacts between adjacent rows.

    First apply the established ownership filter. Then inspect a slightly wider
    unfiltered raster. A mixed component may be split only when it is strongly
    anchored in the target row and in an adjacent row and the contact across the
    target-core edge is one or two 8-connected edges. The algorithm never
    removes a target-core pixel.
    """
    cleaned, removed = base_owned_row_crop(
        page_image, row, box, threshold=threshold, probe_y=probe_y
    )
    x0, y0, x1, y1 = map(int, box)
    if probe_y <= 0 or cleaned.width <= 0 or cleaned.height <= 0:
        return cleaned, removed

    probe_top = max(0, y0 - int(probe_y))
    probe_bottom = min(page_image.height, y1 + int(probe_y))
    region = page_image.crop((x0, probe_top, x1, probe_bottom)).convert("L")
    rp = region.load()
    ink = {
        (x, y)
        for y in range(region.height)
        for x in range(region.width)
        if rp[x, y] < threshold
    }
    if not ink:
        return cleaned, removed

    crop_top = y0 - probe_top
    crop_bottom = y1 - probe_top
    core_top = max(crop_top, int(row["page_top"]) - probe_top)
    core_bottom = min(crop_bottom, int(row["page_bottom"]) - probe_top)

    def neighbor_bounds(neighbor):
        if neighbor is None:
            return None, None
        return (
            max(0, int(neighbor["page_top"]) - probe_top),
            min(region.height, int(neighbor["page_bottom"]) - probe_top),
        )

    above_top, above_bottom = neighbor_bounds(neighbor_above)
    below_top, below_bottom = neighbor_bounds(neighbor_below)

    foreign: set[tuple[int, int]] = set()
    for component in _components(ink):
        foreign.update(
            _foreign_edge_pixels(
                component,
                crop_top=crop_top,
                crop_bottom=crop_bottom,
                core_top=core_top,
                core_bottom=core_bottom,
                neighbor_core_top=above_top,
                neighbor_core_bottom=above_bottom,
                side="above",
            )
        )
        foreign.update(
            _foreign_edge_pixels(
                component,
                crop_top=crop_top,
                crop_bottom=crop_bottom,
                core_top=core_top,
                core_bottom=core_bottom,
                neighbor_core_top=below_top,
                neighbor_core_bottom=below_bottom,
                side="below",
            )
        )

    if not foreign:
        return cleaned, removed

    out = cleaned.copy()
    op = out.load()
    newly_removed = 0
    for x, region_y in foreign:
        crop_y = region_y - crop_top
        if 0 <= x < out.width and 0 <= crop_y < out.height and op[x, crop_y] < threshold:
            op[x, crop_y] = 255
            newly_removed += 1
    return out, removed + newly_removed
