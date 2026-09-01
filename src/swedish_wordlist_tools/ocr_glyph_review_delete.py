from __future__ import annotations

import json
from pathlib import Path

from . import ocr_review_row_glyphs_html as legacy


def delete_exact_model(
    payload: dict,
    *,
    label: str,
    style: str,
    pixels_relative_to_baseline: list[list[int]],
) -> int:
    """Delete exactly one facit glyph identified by label, style and raster."""
    target = tuple(tuple(point) for point in pixels_relative_to_baseline)
    glyphs = payload.get("glyphs") or []
    matches: list[int] = []
    for index, glyph in enumerate(glyphs):
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == label and glyph.get("style") == style and pixels == target:
            matches.append(index)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one facit model for {label!r}/{style}, found {len(matches)}"
        )
    del glyphs[matches[0]]
    return 1


def apply_edit_with_delete(
    original_apply_edit,
    state: dict,
    facit: Path,
    form: dict[str, list[str]],
) -> str:
    """Handle delete locally and delegate every other edit to the captured original."""
    action = (form.get("action") or [""])[0]
    if action != "delete":
        return original_apply_edit(state, facit, form)

    ids = [item for item in (form.get("selected") or [""])[0].split(",") if item]
    pixel_value = (form.get("selected_pixels") or [""])[0]
    if pixel_value.strip():
        raise ValueError("Radera glyphmodell använder vald matchad glyph, inte handvalda pixlar")
    if len(ids) != 1 or not ids[0].startswith("M"):
        raise ValueError("Radera kräver exakt en vald matchad glyph")

    index = int(ids[0][1:])
    if not 0 <= index < len(state.get("matches") or []):
        raise ValueError("vald matchad glyph finns inte i aktuell rad")
    match = state["matches"][index]
    pixels = legacy.normalize_points(set(match.pixels), int(match.baseline))

    payload = json.loads(facit.read_text(encoding="utf-8"))
    delete_exact_model(
        payload,
        label=match.label,
        style=match.style,
        pixels_relative_to_baseline=pixels,
    )
    facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"raderad glyphmodell: {match.label!r}/{match.style}"


def render_html_with_delete(original_render, state: dict, message: str = "") -> str:
    """Inject a delete action into the existing hybrid editor without duplicating its UI."""
    html = original_render(state, message)
    needle = '<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>'
    button = (
        needle
        + '\n<button name="action" value="delete" type="submit" formnovalidate '
        + 'onclick="return confirm(\'Radera den valda glyphmodellen ur facit?\')">'
        + 'Radera vald glyphmodell</button>'
    )
    if needle not in html:
        raise ValueError("could not find relabel button in glyph editor HTML")
    return html.replace(needle, button, 1)
