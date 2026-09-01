from __future__ import annotations

import base64
import io
from typing import Any


def _png_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def add_neighbor_row_raster(
    context: dict[str, Any],
    state: dict[str, Any],
    *,
    probe_y: int = 8,
) -> dict[str, Any]:
    """Attach a narrow source raster above/below the physical target row.

    This is diagnostic only.  It deliberately uses the unfiltered source image
    so accidental contacts between target-row ink and a neighbouring row remain
    visible.  Coordinates are relative to the returned diagnostic raster.
    """
    page = context["page"]
    column = int(state["column"])
    row_index = int(state["row"])
    row = context["row_map"]["columns"][column]["rows"][row_index]

    crop_left, _crop_top, crop_right, _crop_bottom = map(int, state["crop_box"])
    source_top = max(0, int(row["page_top"]) - max(0, int(probe_y)))
    source_bottom = min(page.height, int(row["page_bottom"]) + max(0, int(probe_y)))
    image = page.crop((crop_left, source_top, crop_right, source_bottom)).convert("L")

    core_top = max(0, min(image.height, int(row["page_top"]) - source_top))
    core_bottom = max(core_top, min(image.height, int(row["page_bottom"]) - source_top))

    state = dict(state)
    state.update(
        {
            "neighbor_raster_image": _png_data_uri(image),
            "neighbor_raster_width": image.width,
            "neighbor_raster_height": image.height,
            "neighbor_core_top": core_top,
            "neighbor_core_bottom": core_bottom,
            "neighbor_probe_y": int(probe_y),
            "neighbor_page_top": source_top,
            "neighbor_page_bottom": source_bottom,
        }
    )
    return state
