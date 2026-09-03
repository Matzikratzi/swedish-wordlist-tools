from __future__ import annotations

import json
from pathlib import Path

from . import ocr_glyph_matcher as matcher
from . import ocr_review_row_glyphs_html as legacy


FACIT_V2 = "saol14-manual-glyph-facit-v2"
TYPOGRAPHIC_STYLES = {"roman", "italic", "bold"}
_original_load_facit = matcher.load_facit


class _RoleWithTypography(str):
    """Matcher-compatible v2 role string carrying typography for the UI."""

    def __new__(cls, role: str, typographic_style: str):
        obj = str.__new__(cls, role)
        obj.typographic_style = typographic_style
        return obj


def load_facit_with_typography(path: Path) -> list[matcher.GlyphModel]:
    """Keep v2 semantic role for matching while retaining roman/italic/bold."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FACIT_V2:
        return _original_load_facit(path)

    out: list[matcher.GlyphModel] = []
    for row in payload.get("glyphs") or []:
        points = frozenset(
            (int(x), int(y))
            for x, y in row.get("pixels_relative_to_baseline") or []
        )
        if not points:
            continue
        role = str(row.get("role") or "unknown")
        typographic_style = str(row.get("style") or "roman")
        if typographic_style not in TYPOGRAPHIC_STYLES:
            typographic_style = "roman"
        out.append(
            matcher.GlyphModel(
                label=str(row.get("label") or ""),
                style=_RoleWithTypography(role, typographic_style),
                pixels=points,
                sources=len(row.get("sources") or []),
            )
        )
    return out


def _install_typography_loader() -> None:
    """Patch references captured by the fast editor without changing matcher semantics."""
    matcher.load_facit = load_facit_with_typography
    try:
        from . import ocr_review_five_rows_glyphs_fast_html as fast
    except ImportError:
        return
    fast.load_facit = load_facit_with_typography


_install_typography_loader()


def _glyph_style(payload: dict, glyph: dict) -> str:
    """Return the matcher-visible style/role for either facit format."""
    if payload.get("format") == FACIT_V2:
        return str(glyph.get("role") or "unknown")
    return str(glyph.get("style") or "roman")


def _match_typographic_style(match) -> str:
    style = getattr(match.style, "typographic_style", None)
    if style in TYPOGRAPHIC_STYLES:
        return style
    raw = str(match.style)
    return raw if raw in TYPOGRAPHIC_STYLES else "roman"


def delete_exact_model(
    payload: dict,
    *,
    label: str,
    style: str,
    pixels_relative_to_baseline: list[list[int]],
    typographic_style: str | None = None,
) -> int:
    """Delete exactly one facit glyph identified by label, role/style and raster."""
    target = tuple(tuple(point) for point in pixels_relative_to_baseline)
    glyphs = payload.get("glyphs") or []
    matches: list[int] = []
    for index, glyph in enumerate(glyphs):
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") != label or _glyph_style(payload, glyph) != str(style) or pixels != target:
            continue
        if payload.get("format") == FACIT_V2 and typographic_style is not None:
            if str(glyph.get("style") or "roman") != typographic_style:
                continue
        matches.append(index)
    if len(matches) != 1:
        detail = f"/{typographic_style}" if typographic_style else ""
        raise ValueError(
            f"expected exactly one facit model for {label!r}/{style}{detail}, found {len(matches)}"
        )
    del glyphs[matches[0]]
    return 1


def _relabel_v2(state: dict, payload: dict, form: dict[str, list[str]]) -> str:
    ids = [item for item in (form.get("selected") or [""])[0].split(",") if item]
    pixel_value = (form.get("selected_pixels") or [""])[0]
    if pixel_value.strip():
        raise ValueError("Rätta facitmodell använder vald glyph, inte handvalda pixlar")
    if len(ids) != 1 or not ids[0].startswith("M"):
        raise ValueError("Rätta kräver exakt en vald matchad glyph")

    index = int(ids[0][1:])
    if not 0 <= index < len(state.get("matches") or []):
        raise ValueError("vald matchad glyph finns inte i aktuell rad")
    match = state["matches"][index]
    new_label = (form.get("label") or [""])[0]
    new_style = (form.get("style") or ["roman"])[0]
    if not new_label:
        raise ValueError("glyph label may not be empty")
    if new_style not in TYPOGRAPHIC_STYLES:
        raise ValueError(f"ogiltig typografisk stil: {new_style!r}")

    target = tuple(
        tuple(point)
        for point in legacy.normalize_points(set(match.pixels), int(match.baseline))
    )
    old_role = str(match.style)
    old_typography = _match_typographic_style(match)
    found: list[dict] = []
    for glyph in payload.get("glyphs") or []:
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if (
            glyph.get("label") == match.label
            and str(glyph.get("role") or "unknown") == old_role
            and str(glyph.get("style") or "roman") == old_typography
            and pixels == target
        ):
            found.append(glyph)
    if len(found) != 1:
        raise ValueError(
            f"expected exactly one v2 facit model for {match.label!r}/{old_role}/{old_typography}, "
            f"found {len(found)}"
        )
    found[0]["label"] = new_label
    found[0]["style"] = new_style
    return f"rättad: {match.label!r}/{old_typography} → {new_label!r}/{new_style}"


def apply_edit_with_delete(
    original_apply_edit,
    state: dict,
    facit: Path,
    form: dict[str, list[str]],
) -> str:
    """Handle v2 relabel/delete locally and delegate ordinary edits."""
    action = (form.get("action") or [""])[0]
    payload = None
    if action in {"delete", "relabel"}:
        payload = json.loads(facit.read_text(encoding="utf-8"))

    if action == "relabel" and payload.get("format") == FACIT_V2:
        message = _relabel_v2(state, payload, form)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return message

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

    delete_exact_model(
        payload,
        label=match.label,
        style=str(match.style),
        typographic_style=_match_typographic_style(match),
        pixels_relative_to_baseline=pixels,
    )
    facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"raderad glyphmodell: {match.label!r}/{_match_typographic_style(match)}"


def _apply_display_typography(state: dict) -> None:
    """Expose real roman/italic/bold in chips while matches retain v2 role."""
    matches = state.get("matches") or []
    by_id = {
        f"M{index:02d}": match
        for index, match in enumerate(matches)
    }
    for item in state.get("items") or []:
        match = by_id.get(item.get("id"))
        if match is None:
            continue
        item["role"] = str(match.style)
        item["style"] = _match_typographic_style(match)


def render_html_with_delete(original_render, state: dict, message: str = "") -> str:
    """Show true typography and add normal/direct deletion controls."""
    _apply_display_typography(state)
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
