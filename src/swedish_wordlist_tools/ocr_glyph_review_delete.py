from __future__ import annotations

import json
from pathlib import Path

from . import ocr_glyph_matcher as matcher
from . import ocr_review_row_glyphs_html as legacy


FACIT_V2 = "saol14-manual-glyph-facit-v2"
TYPOGRAPHIC_STYLES = {"roman", "italic", "bold"}
_original_load_facit = matcher.load_facit


class _RoleWithTypography(str):
    """Matcher-compatible v2 role string carrying review metadata for the UI."""

    def __new__(cls, role: str, typographic_style: str, reviewed: bool = False):
        obj = str.__new__(cls, role)
        obj.typographic_style = typographic_style
        obj.reviewed = bool(reviewed)
        return obj


def load_facit_with_typography(path: Path) -> list[matcher.GlyphModel]:
    """Keep v2 semantic role while retaining typography and review state."""
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
                style=_RoleWithTypography(
                    role,
                    typographic_style,
                    bool(row.get("reviewed", False)),
                ),
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


def _match_reviewed(match) -> bool:
    return bool(getattr(match.style, "reviewed", False))


def _model_pixels(match) -> tuple[tuple[int, int], ...]:
    return tuple(
        tuple(point)
        for point in legacy.normalize_points(set(match.pixels), int(match.baseline))
    )


def _glyph_matches_model(payload: dict, glyph: dict, match) -> bool:
    pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
    if glyph.get("label") != match.label or pixels != _model_pixels(match):
        return False
    if payload.get("format") == FACIT_V2:
        return (
            str(glyph.get("role") or "unknown") == str(match.style)
            and str(glyph.get("style") or "roman") == _match_typographic_style(match)
        )
    return str(glyph.get("style") or "roman") == str(match.style)


def mark_matches_reviewed(payload: dict, matches, *, reset: bool = False) -> int:
    """Persist review state for the exact facit models represented by matches."""
    if reset:
        for glyph in payload.get("glyphs") or []:
            glyph["reviewed"] = False

    changed = 0
    for match in matches:
        found = [glyph for glyph in payload.get("glyphs") or [] if _glyph_matches_model(payload, glyph, match)]
        if len(found) != 1:
            raise ValueError(
                f"expected exactly one facit model for reviewed {match.label!r}/"
                f"{_match_typographic_style(match)}, found {len(found)}"
            )
        if not bool(found[0].get("reviewed", False)):
            found[0]["reviewed"] = True
            changed += 1
    return changed


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

    target = _model_pixels(match)
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
    found[0]["reviewed"] = True
    return f"rättad/godkänd: {match.label!r}/{old_typography} → {new_label!r}/{new_style}"


def _mark_added_reviewed(state: dict, payload: dict, form: dict[str, list[str]]) -> None:
    label = (form.get("label") or [""])[0]
    style = (form.get("style") or ["roman"])[0]
    ids = [item for item in (form.get("selected") or [""])[0].split(",") if item]
    pixel_value = (form.get("selected_pixels") or [""])[0]
    source_ink = {tuple(point) for point in state.get("source_ink_points") or []}
    pixel_points = legacy.parse_pixel_selection(pixel_value, source_ink) if pixel_value.strip() else set()
    points = pixel_points if pixel_points else legacy.selected_points(state, ids)
    target = tuple(
        tuple(point)
        for point in legacy.normalize_points(points, int(state["baseline"]))
    )
    found = []
    for glyph in payload.get("glyphs") or []:
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == label and str(glyph.get("style") or "roman") == style and pixels == target:
            found.append(glyph)
    if len(found) == 1:
        found[0]["reviewed"] = True


def apply_edit_with_delete(
    original_apply_edit,
    state: dict,
    facit: Path,
    form: dict[str, list[str]],
) -> str:
    """Handle review-aware v2 relabel/delete and ordinary additions."""
    action = (form.get("action") or [""])[0]
    payload = None
    if action in {"delete", "relabel"}:
        payload = json.loads(facit.read_text(encoding="utf-8"))

    if action == "relabel" and payload.get("format") == FACIT_V2:
        message = _relabel_v2(state, payload, form)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return message

    if action not in {"delete", "relabel"}:
        message = original_apply_edit(state, facit, form)
        if action == "add":
            payload = json.loads(facit.read_text(encoding="utf-8"))
            _mark_added_reviewed(state, payload, form)
            facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return message

    if action == "relabel":
        message = original_apply_edit(state, facit, form)
        payload = json.loads(facit.read_text(encoding="utf-8"))
        new_label = (form.get("label") or [""])[0]
        new_style = (form.get("style") or ["roman"])[0]
        for glyph in payload.get("glyphs") or []:
            if glyph.get("label") == new_label and str(glyph.get("style") or "roman") == new_style:
                glyph["reviewed"] = True
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return message

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
    """Expose typography and persisted review state in matched chips."""
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
        item["reviewed"] = _match_reviewed(match)


def _replace_first_variant(html: str, variants: tuple[str, ...], replacement: str, error: str) -> str:
    for needle in variants:
        if needle in html:
            return html.replace(needle, replacement, 1)
    raise ValueError(error)


def render_html_with_delete(original_render, state: dict, message: str = "") -> str:
    """Show review state, prefill matched glyphs and keep the shared delete action."""
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

    style_needle = '</style></head><body>'
    review_style = '''
.chip.match.needs-review .glyph-label{
  text-decoration-line:underline;
  text-decoration-color:#e58a00;
  text-decoration-thickness:3px;
  text-underline-offset:4px;
}
'''
    if style_needle not in html:
        raise ValueError("could not find editor style block")
    html = html.replace(style_needle, review_style + style_needle, 1)

    class_replacement = (
        "b.className='chip '+it.kind+' '+it.style+"
        "((it.kind==='match' && it.reviewed===false)?' needs-review':'');"
    )
    html = _replace_first_variant(
        html,
        ("b.className='chip '+it.kind+' '+it.style;",),
        class_replacement,
        "could not find glyph-chip class assignment",
    )

    click_replacement = """b.onclick=()=>{
   toggle(it.id);
   if(it.kind==='match'){
     document.getElementById('label').value=it.label;
     const styleSelect=document.querySelector('select[name="style"]');
     if(styleSelect) styleSelect.value=it.style;
   }
 };document.getElementById('items').appendChild(b);"""
    html = _replace_first_variant(
        html,
        (
            "b.onclick=()=>toggle(it.id);document.getElementById('items').appendChild(b);",
            "b.onclick=()=>toggle(it.id); document.getElementById('items').appendChild(b);",
        ),
        click_replacement,
        "could not find glyph-chip click handler",
    )
    return html
