from __future__ import annotations

import json
from pathlib import Path

from . import ocr_review_row_glyphs_html as legacy


def _glyph_style(payload: dict, glyph: dict) -> str:
    """Return the matcher-visible style/role for either facit format."""
    if payload.get("format") == "saol14-manual-glyph-facit-v2":
        return str(glyph.get("role") or "unknown")
    return str(glyph.get("style") or "roman")


def delete_exact_model(
    payload: dict,
    *,
    label: str,
    style: str,
    pixels_relative_to_baseline: list[list[int]],
) -> int:
    """Delete exactly one facit glyph identified by label, matcher style and raster."""
    target = tuple(tuple(point) for point in pixels_relative_to_baseline)
    glyphs = payload.get("glyphs") or []
    matches: list[int] = []
    for index, glyph in enumerate(glyphs):
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == label and _glyph_style(payload, glyph) == style and pixels == target:
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
    """Add both the normal delete action and a direct delete button per matched glyph."""
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
    html = html.replace(needle, button, 1)

    # A bad model can have a huge bounding box overlapping many correct glyphs,
    # which makes selecting it on the canvas awkward or impossible. Give every
    # matched chip its own visible delete button. It POSTs the exact Mxx id
    # through the existing form and therefore deletes the exact facit raster.
    direct_delete = r'''
<style>
.glyph-chip-wrap{display:inline-flex;align-items:stretch;gap:2px}
.glyph-chip-delete{padding:3px 6px;border:1px solid #a33;background:#fff;color:#922;font-weight:700}
</style>
<script>
(() => {
  const form=document.getElementById('form');
  const selected=document.getElementById('selected');
  const selectedPixels=document.getElementById('selectedPixels');
  const deleteSubmit=form && form.querySelector('button[name="action"][value="delete"]');
  const items=document.getElementById('items');
  if(!form || !selected || !selectedPixels || !deleteSubmit || !items) return;
  for(const it of S.items){
    if(it.kind!=='match') continue;
    const chip=items.querySelector('.chip[data-id="'+it.id+'"]');
    if(!chip || chip.parentElement.classList.contains('glyph-chip-wrap')) continue;
    const wrap=document.createElement('span');
    wrap.className='glyph-chip-wrap';
    chip.parentNode.insertBefore(wrap,chip);
    wrap.appendChild(chip);
    const del=document.createElement('button');
    del.type='button';
    del.className='glyph-chip-delete';
    del.textContent='×';
    del.title='Radera just '+JSON.stringify(it.label)+' ('+it.pixels+' px) ur facit';
    del.setAttribute('aria-label','Radera glyphmodell '+JSON.stringify(it.label)+' ur facit');
    del.addEventListener('click',()=>{
      if(!confirm('Radera glyphmodellen '+JSON.stringify(it.label)+' ('+it.pixels+' px) ur facit?')) return;
      selected.value=it.id;
      selectedPixels.value='';
      form.requestSubmit(deleteSubmit);
    });
    wrap.appendChild(del);
  }
})();
</script>
'''
    return html.replace("</body>", direct_delete + "</body>", 1)
