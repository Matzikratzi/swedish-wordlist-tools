from __future__ import annotations

from collections import deque
from itertools import product
from typing import Any, Iterable

from PIL import Image

from .ocr_glyph_matcher import GlyphModel, Match, exact_matches, select_best_disjoint_exact


def _components8(ink: set[tuple[int, int]]) -> list[frozenset[tuple[int, int]]]:
    remaining = set(ink)
    out: list[frozenset[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        queue = deque([seed])
        component = {seed}
        while queue:
            x, y = queue.popleft()
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    point = (nx, ny)
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        queue.append(point)
        out.append(frozenset(component))
    return out


def _selected_for_baseline(matches: Iterable[Match], baseline: int) -> list[Match]:
    return select_best_disjoint_exact(match for match in matches if match.baseline == baseline)


def _owned_pixels(matches: Iterable[Match]) -> frozenset[tuple[int, int]]:
    rows = list(matches)
    if not rows:
        return frozenset()
    return frozenset().union(*(match.pixels for match in rows))


def _vertical_order_ok(
    current_owned: frozenset[tuple[int, int]],
    neighbor_owned: frozenset[tuple[int, int]],
    *,
    neighbor_is_below: bool,
) -> bool:
    """Require adjacent-row ownership to preserve vertical order.

    Printed rows may touch, but one row should not weave through the other.
    For the row below, the lowest current-row pixel may be level with the
    highest neighbour pixel, but it may not be lower. The upper-neighbour case
    is the exact mirror image.
    """
    if not current_owned or not neighbor_owned:
        return False
    current_ys = [y for _x, y in current_owned]
    neighbor_ys = [y for _x, y in neighbor_owned]
    if neighbor_is_below:
        return max(current_ys) <= min(neighbor_ys)
    return min(current_ys) >= max(neighbor_ys)


def _exact_two_baseline_partitions(
    component: frozenset[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    current_baselines: range,
    neighbor_baselines: range,
    neighbor_is_below: bool,
) -> list[tuple[frozenset[tuple[int, int]], frozenset[tuple[int, int]], tuple[Match, ...], tuple[Match, ...]]]:
    """Return exact, vertically ordered partitions across two row baselines."""
    if not component:
        return []
    min_x = min(x for x, _ in component)
    min_y = min(y for _, y in component)
    local = frozenset((x - min_x, y - min_y) for x, y in component)
    width = max(x for x, _ in local) + 1
    height = max(y for _, y in local) + 1
    candidates = exact_matches(
        set(local),
        width,
        height,
        models,
        require_whole_components=False,
    )
    if not candidates:
        return []

    current_local = [baseline - min_y for baseline in current_baselines]
    neighbor_local = [baseline - min_y for baseline in neighbor_baselines]
    by_baseline: dict[int, list[Match]] = {}
    for match in candidates:
        by_baseline.setdefault(match.baseline, []).append(match)

    current_choices = [
        (baseline, select_best_disjoint_exact(by_baseline[baseline]))
        for baseline in current_local
        if baseline in by_baseline
    ]
    neighbor_choices = [
        (baseline, select_best_disjoint_exact(by_baseline[baseline]))
        for baseline in neighbor_local
        if baseline in by_baseline
    ]

    valid = []
    for (_current_baseline, current_matches), (_neighbor_baseline, neighbor_matches) in product(
        current_choices, neighbor_choices
    ):
        current_owned = _owned_pixels(current_matches)
        neighbor_owned = _owned_pixels(neighbor_matches)
        if not current_owned or not neighbor_owned:
            continue
        if current_owned.intersection(neighbor_owned):
            continue
        if current_owned.union(neighbor_owned) != local:
            continue
        if not _vertical_order_ok(
            current_owned,
            neighbor_owned,
            neighbor_is_below=neighbor_is_below,
        ):
            continue
        valid.append(
            (
                frozenset((x + min_x, y + min_y) for x, y in current_owned),
                frozenset((x + min_x, y + min_y) for x, y in neighbor_owned),
                tuple(current_matches),
                tuple(neighbor_matches),
            )
        )
    return valid


def split_touching_neighbor_glyphs(
    page_image: Image.Image,
    row_map: dict[str, Any],
    column: int,
    row_index: int,
    box: tuple[int, int, int, int],
    crop: Image.Image,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> tuple[Image.Image, int, list[dict[str, Any]]]:
    """Remove neighbour-owned ink only when exact two-row evidence agrees."""
    models = list(models)
    if not models:
        return crop, 0, []

    columns = row_map.get("columns") or []
    if not 0 <= column < len(columns):
        return crop, 0, []
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        return crop, 0, []

    current = rows[row_index]
    x0, y0, x1, y1 = map(int, box)
    cleaned = crop.copy().convert("L")
    removed_page: set[tuple[int, int]] = set()
    diagnostics: list[dict[str, Any]] = []

    for neighbor_index in (row_index - 1, row_index + 1):
        if not 0 <= neighbor_index < len(rows):
            continue
        neighbor = rows[neighbor_index]
        region_top = max(0, min(int(current["page_top"]), int(neighbor["page_top"])))
        region_bottom = min(page_image.height, max(int(current["page_bottom"]), int(neighbor["page_bottom"])))
        if region_bottom <= region_top:
            continue

        region = page_image.crop((x0, region_top, x1, region_bottom)).convert("L")
        pixels = region.load()
        ink = {
            (x, y)
            for y in range(region.height)
            for x in range(region.width)
            if pixels[x, y] < threshold
        }
        if not ink:
            continue

        current_top = int(current["page_top"]) - region_top
        current_bottom = int(current["page_bottom"]) - region_top
        neighbor_top = int(neighbor["page_top"]) - region_top
        neighbor_bottom = int(neighbor["page_bottom"]) - region_top
        neighbor_is_below = neighbor_index > row_index

        for component in _components8(ink):
            has_current = any(current_top <= y < current_bottom for _x, y in component)
            has_neighbor = any(neighbor_top <= y < neighbor_bottom for _x, y in component)
            if not (has_current and has_neighbor):
                continue

            partitions = _exact_two_baseline_partitions(
                component,
                models,
                current_baselines=range(current_top, current_bottom),
                neighbor_baselines=range(neighbor_top, neighbor_bottom),
                neighbor_is_below=neighbor_is_below,
            )
            if not partitions:
                continue

            neighbor_owners = {partition[1] for partition in partitions}
            if len(neighbor_owners) != 1:
                diagnostics.append(
                    {
                        "neighbor_row": neighbor_index,
                        "status": "ambiguous",
                        "component_pixels": len(component),
                        "partitions": len(partitions),
                    }
                )
                continue

            neighbor_owned = next(iter(neighbor_owners))
            removed_here = 0
            for rx, ry in neighbor_owned:
                page_x = x0 + rx
                page_y = region_top + ry
                if not (x0 <= page_x < x1 and y0 <= page_y < y1):
                    continue
                point = (page_x, page_y)
                if point in removed_page:
                    continue
                crop_x = page_x - x0
                crop_y = page_y - y0
                if 0 <= crop_x < cleaned.width and 0 <= crop_y < cleaned.height:
                    cleaned.putpixel((crop_x, crop_y), 255)
                    removed_page.add(point)
                    removed_here += 1

            if removed_here:
                sample = partitions[0]
                diagnostics.append(
                    {
                        "neighbor_row": neighbor_index,
                        "status": "split",
                        "component_pixels": len(component),
                        "removed_pixels": removed_here,
                        "partitions": len(partitions),
                        "current_labels": "".join(match.label for match in sample[2]),
                        "neighbor_labels": "".join(match.label for match in sample[3]),
                        "vertical_order": "touch-or-gap",
                    }
                )

    return cleaned, len(removed_page), diagnostics
