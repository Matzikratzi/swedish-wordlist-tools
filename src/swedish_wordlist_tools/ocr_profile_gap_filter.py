from __future__ import annotations

from typing import Iterable

from .ocr_whole_column_profile import ProfileExactHit


def horizontal_blank_bands_clear(
    black: set[tuple[int, int]],
    hit: ProfileExactHit,
) -> bool:
    """Require internal blank model rows to be empty across the glyph width.

    Detached glyph parts such as the dot of i/j or the two dots of ':' create
    horizontal blank raster bands inside the glyph's vertical extent.  Those
    bands are allowed to show unrelated ink in the whole-column 1D profile, but
    the placed glyph itself must be empty across its own horizontal x span.
    """
    model = hit.model
    occupied_y = {y for _x, y in model.pixels}
    min_model_x = min(x for x, _y in model.pixels)
    max_model_x = max(x for x, _y in model.pixels)
    for model_y in range(model.min_y, model.max_y + 1):
        if model_y in occupied_y:
            continue
        page_y = hit.baseline + model_y
        for page_x in range(hit.x + min_model_x, hit.x + max_model_x + 1):
            if (page_x, page_y) in black:
                return False
    return True


def filter_horizontal_blank_bands(
    black: set[tuple[int, int]],
    hits: Iterable[ProfileExactHit],
) -> tuple[ProfileExactHit, ...]:
    return tuple(hit for hit in hits if horizontal_blank_bands_clear(black, hit))
