from __future__ import annotations

import json
import sys
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
    matcher.load_facit = load_facit_with_typography
    try:
        from . import ocr_review_five_rows_glyphs_fast_html as fast
    except ImportError:
        return
    fast.load_facit = load_facit_with_typography


_install_typography_loader()


def _glyph_style(payload: dict, glyph: dict) -> str:
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
    return tuple(tuple(point) for point in legacy.normalize_points(set(match.pixels), int(match.baseline)))


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
    if reset:
        for glyph in payload.get("glyphs") or []:
            glyph["reviewed"] = False
    changed = 0
    for match in matches:
        found = [glyph for glyph in payload.get("glyphs") or [] if _glyph_matches_model(payload, glyph, match)]
        if len(found) != 1:
            raise ValueError(f"expected exactly one facit model for reviewed {match.label!r}/{_match_typographic_style(match)}, found {len(found)}")
        if not bool(found[0].get("reviewed", False)):
            found[0]["reviewed"] = True
            changed += 1
    return changed


def delete_exact_model(payload: dict, *, label: str, style: str, pixels_relative_to_baseline: list[list[int]], typographic_style: str | None = None) -> int:
    target = tuple(tuple(point) for point in pixels_relative_to_baseline)
    glyphs = payload.get("glyphs") or []
    matches: list[int] = []
    for index, glyph in enumerate(glyphs):
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") != label or _glyph_style(payload, glyph) != str(style) or pixels != target:
            continue
        if payload.get("format") == FACIT_V2 and typographic_style is not None and str(glyph.get("style") or "roman") != typographic_style:
            continue
        matches.append(index)
    if len(matches) != 1:
        detail = f"/{typographic_style}" if typographic_style else ""
        raise ValueError(f"expected exactly one facit model for {label!r}/{style}{detail}, found {len(matches)}")
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
    found = []
    for glyph in payload.get("glyphs") or []:
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == match.label and str(glyph.get("role") or "unknown") == old_role and str(glyph.get("style") or "roman") == old_typography and pixels == target:
            found.append(glyph)
    if len(found) != 1:
        raise ValueError(f"expected exactly one v2 facit model for {match.label!r}/{old_role}/{old_typography}, found {len(found)}")
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
    target = tuple(tuple(point) for point in legacy.normalize_points(points, int(state["baseline"])))
    found = []
    for glyph in payload.get("glyphs") or []:
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == label and str(glyph.get("style") or "roman") == style and pixels == target:
            found.append(glyph)
    if len(found) == 1:
        found[0]["reviewed"] = True


def _pixel_context_for_state(state: dict) -> dict | None:
    module = sys.modules.get("swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html")
    context = getattr(module, "_current_pixel_context", None) if module is not None else None
    if not context or int(context.get("page_number", -1)) != int(state.get("page", -2)):
        return None
    return context


def _source_is_black(context: dict, x: int, y: int) -> bool:
    page = context["pixel_gray_page"]
    if not (0 <= x < page.width and 0 <= y < page.height):
        return False
    return int(page.getpixel((x, y))) < int(context.get("threshold", 210))


def _connected_source_component(context: dict, seeds: set[tuple[int, int]], box: tuple[int, int, int, int]) -> set[tuple[int, int]]:
    left, top, right, bottom = map(int, box)
    pending = [point for point in seeds if left <= point[0] < right and top <= point[1] < bottom and _source_is_black(context, *point)]
    seen = set(pending)
    while pending:
        x, y = pending.pop()
        for ny in range(y - 1, y + 2):
            for nx in range(x - 1, x + 2):
                if (nx, ny) == (x, y) or (nx, ny) in seen:
                    continue
                if not (left <= nx < right and top <= ny < bottom):
                    continue
                if not _source_is_black(context, nx, ny):
                    continue
                seen.add((nx, ny))
                pending.append((nx, ny))
    return seen


def manual_two_row_candidates(context: dict, state: dict) -> list[dict]:
    """Find residual source components that actually cross an adjacent row separator."""
    if int(state.get("covered_pixels") or 0) == int(state.get("source_pixels") or 0):
        return []
    column = int(state["column"])
    row_index = int(state["row"])
    columns = context.get("row_map", {}).get("columns") or []
    if not 0 <= column < len(columns):
        return []
    column_entry = columns[column]
    rows = column_entry.get("rows") or []
    if not 0 <= row_index < len(rows):
        return []
    crop_left, crop_top, _crop_right, _crop_bottom = map(int, state["crop_box"])
    owners = context["pixel_owners"]
    left = max(0, int(column_entry.get("crop_left", column_entry.get("left", 0))))
    right = min(owners.width, int(column_entry.get("crop_right", column_entry.get("right", owners.width))))

    pairs: list[tuple[int, int, int]] = []
    if row_index > 0:
        pairs.append((row_index - 1, row_index, int(rows[row_index - 1]["page_bottom"])))
    if row_index + 1 < len(rows):
        pairs.append((row_index, row_index + 1, int(rows[row_index]["page_bottom"])))

    candidates: list[dict] = []
    seen_components: set[tuple[int, int, frozenset[tuple[int, int]]]] = set()
    for item in state.get("items") or []:
        if item.get("kind") != "residual":
            continue
        local_points = set((state.get("point_sets") or {}).get(item.get("id")) or [])
        if not local_points:
            continue
        page_points = {(crop_left + int(x), crop_top + int(y)) for x, y in local_points}
        for upper_row, lower_row, separator in pairs:
            edge_points = {
                (x, y)
                for x, y in page_points
                if abs(y - separator) <= 1
                or y == separator - 1
            }
            if not edge_points:
                continue
            has_cross_link = False
            for x, y in edge_points:
                if y < separator:
                    other_y = separator
                else:
                    other_y = separator - 1
                if any(_source_is_black(context, nx, other_y) for nx in (x - 1, x, x + 1)):
                    has_cross_link = True
                    break
            if not has_cross_link:
                continue
            scan_top = max(0, int(rows[upper_row]["page_top"]) - 2)
            scan_bottom = min(owners.height, int(rows[lower_row]["page_bottom"]) + 2)
            component = _connected_source_component(context, page_points, (left, scan_top, right, scan_bottom))
            if not component or not any(y < separator for _x, y in component) or not any(y >= separator for _x, y in component):
                continue
            key = (upper_row, lower_row, frozenset(component))
            if key in seen_components:
                continue
            seen_components.add(key)
            upper_code = owners.row_code(upper_row)
            lower_code = owners.row_code(lower_row)
            upper_owned = sum(1 for x, y in component if owners.value(x, y) == upper_code)
            lower_owned = sum(1 for x, y in component if owners.value(x, y) == lower_code)
            neighbor_top = int(state.get("neighbor_page_top", scan_top))
            candidates.append({
                "id": len(candidates),
                "upper_row": upper_row,
                "lower_row": lower_row,
                "separator_page_y": separator,
                "component_pixels": sorted(component),
                "neighbor_pixels": [[x - crop_left, y - neighbor_top] for x, y in sorted(component)],
                "pixels": len(component),
                "upper_owned": upper_owned,
                "lower_owned": lower_owned,
                "residual_ids": [item.get("id")],
            })
    return candidates


def _apply_manual_two_row_ownership(state: dict, form: dict[str, list[str]]) -> str:
    context = _pixel_context_for_state(state)
    if context is None:
        raise ValueError("tvåradsägande finns bara i byte-array-editorn")
    try:
        candidate_index = int((form.get("ownership_candidate") or [""])[0])
    except ValueError as exc:
        raise ValueError("ogiltig tvåradskandidat") from exc
    action = (form.get("action") or [""])[0]
    candidates = manual_two_row_candidates(context, state)
    if not 0 <= candidate_index < len(candidates):
        raise ValueError("tvåradskandidaten finns inte längre; räkna om raden")
    candidate = candidates[candidate_index]
    if action == "ownership_upper":
        target_row = int(candidate["upper_row"])
    elif action == "ownership_lower":
        target_row = int(candidate["lower_row"])
    else:
        raise ValueError(f"okänd tvåradsåtgärd: {action!r}")
    owners = context["pixel_owners"]
    target_code = owners.row_code(target_row)
    changed = 0
    with context["known_glyph_ownership_lock"]:
        for x, y in candidate["component_pixels"]:
            offset = y * owners.width + x
            if owners.data[offset] != target_code:
                owners.data[offset] = target_code
                changed += 1
        if changed:
            context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
            revisions = context["pixel_owner_row_revisions"]
            for position in (
                (int(state["column"]), int(candidate["upper_row"])),
                (int(state["column"]), int(candidate["lower_row"])),
            ):
                revisions[position] = int(revisions.get(position, 0)) + 1
            context.setdefault("manual_two_row_ownership", []).append({
                "column": int(state["column"]),
                "upper_row": int(candidate["upper_row"]),
                "lower_row": int(candidate["lower_row"]),
                "target_row": target_row,
                "pixels": int(candidate["pixels"]),
                "changed": changed,
            })
    return (
        f"tvåradsägande: komponent {candidate_index + 1} → rad {target_row}; "
        f"{changed} pixlar flyttade"
    )


def apply_edit_with_delete(original_apply_edit, state: dict, facit: Path, form: dict[str, list[str]]) -> str:
    action = (form.get("action") or [""])[0]
    if action in {"ownership_upper", "ownership_lower"}:
        return _apply_manual_two_row_ownership(state, form)

    payload = None
    if action in {"delete", "relabel"}:
        payload = json.loads(facit.read_text(encoding="utf-8"))
    if action == "relabel" and payload.get("format") == FACIT_V2:
        message = _relabel_v2(state, payload, form)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return message
    if action not in {"delete", "relabel"}:
        message = original_apply_edit(state, facit, form)
        if action == "add" and facit.exists():
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
    delete_exact_model(payload, label=match.label, style=str(match.style), typographic_style=_match_typographic_style(match), pixels_relative_to_baseline=pixels)
    facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"raderad glyphmodell: {match.label!r}/{_match_typographic_style(match)}"


def _apply_display_typography(state: dict) -> None:
    matches = state.get("matches") or []
    by_id = {f"M{index:02d}": match for index, match in enumerate(matches)}
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


def _manual_two_row_panel(state: dict) -> str:
    context = _pixel_context_for_state(state)
    if context is None:
        return ""
    candidates = manual_two_row_candidates(context, state)
    if not candidates:
        return ""
    blocks = []
    for candidate in candidates:
        upper = candidate["upper_row"]
        lower = candidate["lower_row"]
        index = candidate["id"]
        blocks.append(
            '<div class="two-row-candidate">'
            f'<b>Brygga rad {upper}/{lower}</b>: sammanhängande komponent {candidate["pixels"]} px '
            f'({candidate["upper_owned"]} hos rad {upper}, {candidate["lower_owned"]} hos rad {lower}). '
            '<form method="post" class="two-row-form">'
            f'<input type="hidden" name="ownership_candidate" value="{index}">'
            f'<button name="action" value="ownership_upper" type="submit">Hela komponenten → rad {upper}</button> '
            f'<button name="action" value="ownership_lower" type="submit">Hela komponenten → rad {lower}</button>'
            '</form></div>'
        )
    return (
        '<section class="two-row-fallback">'
        '<h2>Tvåradsgranskning</h2>'
        '<p>En omatchad komponent korsar en radgräns och kunde inte avgöras med en känd facitglyph. '
        'Tre-radersrastret öppnas automatiskt. Välj vilken fysisk rad hela den sammanhängande komponenten hör till.</p>'
        + ''.join(blocks)
        + '</section>'
    )


def render_html_with_delete(original_render, state: dict, message: str = "") -> str:
    _apply_display_typography(state)
    html = original_render(state, message)
    needle = '<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>'
    button = needle + '\n<button name="action" value="delete" type="submit" formnovalidate onclick="return confirm(\'Radera den valda glyphmodellen ur facit?\')">Radera vald glyphmodell</button>'
    if needle not in html:
        raise ValueError("could not find relabel button in glyph editor HTML")
    html = html.replace(needle, button, 1)
    style_needle = '</style></head><body>'
    if style_needle not in html:
        return html
    review_style = '''
.chip{min-width:0;padding:3px 4px}
.glyph-label{font-size:20px;line-height:1;min-width:0}
.chip.italic .glyph-label{font-style:italic;font-weight:400}
.chip.roman .glyph-label{font-style:normal;font-weight:400}
.chip.bold .glyph-label{font-style:normal;font-weight:700}
.pixel-count{font-size:11px;line-height:1;font-weight:400;text-align:center}
.pixel-unit{display:block;font-size:9px;line-height:1;margin-top:1px}
.rowbox + .items{margin-top:6px}
.row-summary code{font-size:2em;line-height:1.15}
.chip.match.needs-review .glyph-label{
  text-decoration-line:underline;
  text-decoration-color:#e58a00;
  text-decoration-thickness:3px;
  text-underline-offset:4px;
}
.two-row-fallback{max-width:1100px;border:2px solid #c77b00;background:#fff7e6;padding:10px 12px;margin:10px 0 14px}
.two-row-fallback h2{font-size:18px;margin:0 0 5px}.two-row-fallback p{margin:4px 0 8px}
.two-row-candidate{padding:7px 0;border-top:1px solid #e0bf7c}.two-row-form{display:inline-block;margin-left:8px}.two-row-form button{padding:4px 7px}
'''
    html = html.replace(style_needle, review_style + style_needle, 1)
    html = html.replace('<div>Exakt:', '<div class="row-summary">Exakt:', 1)
    class_replacement = "b.className='chip '+it.kind+' '+it.style+((it.kind==='match' && it.reviewed===false)?' needs-review':'');"
    html = _replace_first_variant(html, ("b.className='chip '+it.kind+' '+it.style;",), class_replacement, "could not find glyph-chip class assignment")
    html = _replace_first_variant(html, ("glyph.textContent=JSON.stringify(it.label);",), "glyph.textContent=it.label;", "could not find glyph label renderer")
    pixel_needle = "pixels.textContent=it.pixels+' px';"
    pixel_replacement = "pixels.textContent=it.pixels;const unit=document.createElement('span');unit.className='pixel-unit';unit.textContent='px';pixels.appendChild(unit);"
    if html.count(pixel_needle) != 2:
        raise ValueError("could not find both glyph pixel-count renderers")
    html = html.replace(pixel_needle, pixel_replacement)

    toggle_needle = "function toggle(id){chosen.has(id)?chosen.delete(id):chosen.add(id);sync();}"
    toggle_replacement = r'''const orderedItems=[...S.items].sort((a,b)=>{
 const ax=a.bbox?a.bbox.left:0,bx=b.bbox?b.bbox.left:0;
 if(ax!==bx)return ax-bx;
 const ay=a.bbox?a.bbox.top:0,by=b.bbox?b.bbox.top:0;
 return ay-by || String(a.id).localeCompare(String(b.id));
});
function replaceSet(target,next){target.clear();for(const value of next)target.add(value);}
function toggle(id){chosen.has(id)?chosen.delete(id):chosen.add(id);sync();return true;}'''
    html = _replace_first_variant(html, (toggle_needle,), toggle_replacement, "could not find glyph selection toggle")

    click_replacement = r'''b.onclick=()=>{
   toggle(it.id);
   prefillItem(it);
 };document.getElementById('items').appendChild(b);'''
    old_click_variants = (
        "b.onclick=()=>toggle(it.id);document.getElementById('items').appendChild(b);",
        "b.onclick=()=>toggle(it.id); document.getElementById('items').appendChild(b);",
    )
    prefill_script = r'''function prefillItem(it){
 const styleSelect=document.querySelector('select[name="style"]');
 if(styleSelect){
   const matchedItems=S.items.filter(candidate=>candidate.kind==='match');
   let leftItem=null;
   if(it.bbox){
     leftItem=matchedItems.filter(candidate=>candidate.id!==it.id && candidate.bbox && candidate.bbox.left<it.bbox.left).sort((a,b)=>b.bbox.left-a.bbox.left)[0] || null;
   }
   if(!leftItem){
     const itemIndex=S.items.findIndex(candidate=>candidate.id===it.id);
     leftItem=itemIndex>0 ? S.items.slice(0,itemIndex).reverse().find(candidate=>candidate.kind==='match') : null;
   }
   if(leftItem)styleSelect.value=leftItem.style;
   else if(it.kind==='match')styleSelect.value=it.style;
 }
 if(it.kind==='match')document.getElementById('label').value=it.label;
}
'''
    html = _replace_first_variant(
        html,
        old_click_variants,
        click_replacement,
        "could not find glyph-chip click handler",
    )
    loop_needle = "for(const it of S.items){\n const b=document.createElement('button');"
    if loop_needle not in html:
        raise ValueError("could not find glyph item button loop")
    html = html.replace(loop_needle, prefill_script + loop_needle, 1)

    arrow_script = r'''
window.addEventListener('keydown',e=>{
 if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
 const active=document.activeElement;
 if(active && ['INPUT','SELECT','TEXTAREA'].includes(active.tagName))return;
 if(chosen.size!==1 || chosenPixels.size)return;
 const current=[...chosen][0],index=orderedItems.findIndex(it=>it.id===current);
 if(index<0)return;
 const target=orderedItems[index+(e.key==='ArrowLeft'?-1:1)];
 if(!target)return;
 e.preventDefault();
 replaceSet(chosen,new Set([target.id]));sync();prefillItem(target);
 const button=document.querySelector('.chip[data-id="'+target.id+'"]');if(button)button.focus();
});
'''
    html = html.replace('</script></body></html>', arrow_script + '</script></body></html>', 1)

    panel = _manual_two_row_panel(state)
    if panel:
        form_needle = '<form method="post" id="form">'
        if form_needle not in html:
            raise ValueError("could not find glyph form for two-row fallback")
        html = html.replace(form_needle, panel + form_needle, 1)
        html = html.replace(
            '</body>',
            '''<script>document.addEventListener('DOMContentLoaded',()=>{const c=document.getElementById('showNeighbors');if(c){c.checked=true;c.dispatchEvent(new Event('change'));}});</script></body>''',
            1,
        )
    return html


legacy.apply_edit = (lambda original: lambda state, facit, form: apply_edit_with_delete(original, state, facit, form))(legacy.apply_edit)
legacy.render_html = (lambda original: lambda state, message="": render_html_with_delete(original, state, message))(legacy.render_html)
