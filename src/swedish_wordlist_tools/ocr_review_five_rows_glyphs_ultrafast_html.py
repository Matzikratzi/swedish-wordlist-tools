from __future__ import annotations

import html
import json
import threading

from . import ocr_review_five_rows_glyphs_fast_html as fast
from .ocr_glyph_review_delete import apply_edit_with_delete, render_html_with_delete
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped
from .ocr_two_row_glyph_ownership import split_touching_neighbor_glyphs


# The fast editor already reuses page geometry, keeps generation-aware row
# state, and prevents duplicate concurrent work. Its remaining hot path is the
# whole-row exact matcher imported into that module as ``analyse_row_exact``.
# Swap only that implementation for the previously verified safe-gap grouped
# matcher. ``load_review_state_fast`` resolves the module global at call time,
# so no other editor behaviour changes.
fast.analyse_row_exact = analyse_row_exact_grouped

# Add two-row ownership evidence without changing the base editor API. The fast
# loader calls its module-global _owned_row_crop; keep the context/models for
# the current row in thread-local storage while that call runs. This is safe
# with the five parallel row workers used by the editor.
_original_owned_row_crop = fast._owned_row_crop
_ownership_context = threading.local()


def owned_row_crop_with_two_row_evidence(page_image, row, box, *, threshold=210, probe_y=6):
    crop, removed = _original_owned_row_crop(
        page_image,
        row,
        box,
        threshold=threshold,
        probe_y=probe_y,
    )
    active = getattr(_ownership_context, "active", None)
    if active is None:
        return crop, removed
    context, position, models = active
    if page_image is not context.get("page"):
        return crop, removed

    column, row_index = position
    rows = (context.get("row_map", {}).get("columns") or [])[column].get("rows") or []
    if not 0 <= row_index < len(rows) or rows[row_index] is not row:
        return crop, removed

    cleaned, split_removed, diagnostics = split_touching_neighbor_glyphs(
        page_image,
        context["row_map"],
        column,
        row_index,
        box,
        crop,
        models,
        threshold=threshold,
    )
    _ownership_context.two_row_removed = split_removed
    _ownership_context.two_row_diagnostics = diagnostics
    return cleaned, removed + split_removed


fast._owned_row_crop = owned_row_crop_with_two_row_evidence

# Add an unfiltered narrow source raster around the target row. The ordinary
# matching crop now also gets the conservative two-row exact-glyph ownership
# split above.
_original_load_review_state_fast = fast.load_review_state_fast


def load_review_state_with_neighbors(context, position, models):
    _ownership_context.active = (context, position, models)
    _ownership_context.two_row_removed = 0
    _ownership_context.two_row_diagnostics = []
    try:
        state = _original_load_review_state_fast(context, position, models)
        state["two_row_removed_pixels"] = int(getattr(_ownership_context, "two_row_removed", 0))
        state["two_row_ownership"] = list(getattr(_ownership_context, "two_row_diagnostics", []))
    finally:
        for name in ("active", "two_row_removed", "two_row_diagnostics"):
            if hasattr(_ownership_context, name):
                delattr(_ownership_context, name)
    return add_neighbor_row_raster(context, state, probe_y=8)


fast.load_review_state_fast = load_review_state_with_neighbors

# Add a narrowly scoped destructive action to the same editor. Keep references
# to the original renderer and edit handler before monkeypatching so wrappers
# cannot recurse.
_original_render_html = fast.ui.editor.render_html
_original_apply_edit = fast.legacy.apply_edit


def diagnostic_text(state: dict) -> str:
    """Return a compact, paste-friendly description of the active review row."""
    lines = [
        "SAOL GLYPH REVIEW",
        f"page={state.get('page')} column={state.get('column')} row={state.get('row')}",
        f"crop_box={state.get('crop_box')}",
        f"row_page={state.get('row_page_top')}..{state.get('row_page_bottom')}",
        f"baseline={state.get('baseline')}",
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} fully_exact={state.get('fully_exact')}",
        f"removed_neighbor_pixels={state.get('removed_neighbor_pixels', 0)}",
        f"two_row_removed_pixels={state.get('two_row_removed_pixels', 0)}",
        f"text={state.get('text', '')!r}",
        f"markup={state.get('markup', '')!r}",
    ]
    ownership = state.get("two_row_ownership") or []
    if ownership:
        lines.append("two_row_ownership:")
        for item in ownership:
            lines.append("  " + json.dumps(item, ensure_ascii=False, sort_keys=True))
    if state.get("neighbor_raster_image"):
        lines.extend(
            [
                "neighbor_raster:",
                f"  size={state.get('neighbor_raster_width')}x{state.get('neighbor_raster_height')}",
                f"  probe_y={state.get('neighbor_probe_y')}",
                f"  page_y={state.get('neighbor_page_top')}..{state.get('neighbor_page_bottom')}",
                f"  core_y={state.get('neighbor_core_top')}..{state.get('neighbor_core_bottom')}",
            ]
        )
    lines.append("items:")
    for item in state.get("items") or []:
        lines.append(
            "  "
            + f"{item.get('id')} kind={item.get('kind')} label={item.get('label')!r} "
            + f"style={item.get('style')} pixels={item.get('pixels')} bbox={item.get('bbox')}"
        )
    source_points = state.get("source_ink_points") or []
    lines.append(f"source_ink_pixels={len(source_points)}")
    return "\n".join(lines) + "\n"


def render_html_with_neighbor_raster(state, message=""):
    document = render_html_with_delete(_original_render_html, state, message)

    diagnostics = diagnostic_text(state)
    diag_json = json.dumps(diagnostics, ensure_ascii=False).replace("</", "<\\/")
    controls_needle = '<span id="pixelCount">0 valda pixlar</span>\n</div>'
    controls = '<span id="pixelCount">0 valda pixlar</span>\n'
    if state.get("neighbor_raster_image"):
        controls += '<label class="inline"><input type="checkbox" id="showNeighbors"> Visa grannrader</label>\n'
    controls += '<button type="button" id="copyDiagnostics">Kopiera diagnostik</button>\n</div>'
    if controls_needle not in document:
        raise ValueError("could not find editor controls for diagnostics")
    document = document.replace(controls_needle, controls, 1)

    if state.get("neighbor_raster_image"):
        rowbox_needle = '<div class="rowbox"><canvas id="row"></canvas></div>'
        neighbor_box = rowbox_needle + '''
<div id="neighborWrap" style="display:none;margin:10px 0 18px">
  <div><b>Grannradsraster</b> – ofiltrerad källa. Röda linjer avgränsar målradens egentliga område; pixlar ovanför/under är endast observation.</div>
  <div class="rowbox" style="padding-top:36px"><canvas id="neighborRow"></canvas></div>
</div>'''
        if rowbox_needle not in document:
            raise ValueError("could not find editor row canvas for neighbor raster")
        document = document.replace(rowbox_needle, neighbor_box, 1)

    script = r'''
<script>
(() => {
  const diagnostics=__DIAGNOSTICS__;
  const copyButton=document.getElementById('copyDiagnostics');
  if(copyButton){
    copyButton.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(diagnostics);
        copyButton.textContent='Kopierat!';
      } catch(err) {
        const ta=document.createElement('textarea');
        ta.value=diagnostics;ta.style.position='fixed';ta.style.left='-9999px';
        document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
        copyButton.textContent='Kopierat!';
      }
      setTimeout(()=>copyButton.textContent='Kopiera diagnostik',1200);
    });
  }

  const checkbox=document.getElementById('showNeighbors');
  const wrap=document.getElementById('neighborWrap');
  const canvas=document.getElementById('neighborRow');
  if(!checkbox || !wrap || !canvas || !S.neighbor_raster_image) return;
  const ctx=canvas.getContext('2d'), nscale=7, ntop=34;
  const nimg=new Image(); nimg.src=S.neighbor_raster_image;
  function drawNeighbor(){
    canvas.width=S.neighbor_raster_width*nscale;
    canvas.height=S.neighbor_raster_height*nscale+ntop;
    ctx.imageSmoothingEnabled=false;
    ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(nimg,0,ntop,S.neighbor_raster_width*nscale,S.neighbor_raster_height*nscale);

    // Same visible pixel grid as the main glyph editor.
    ctx.save();ctx.strokeStyle='rgba(70,70,70,.22)';ctx.lineWidth=1;
    for(let x=0;x<=S.neighbor_raster_width;x++){
      const xx=x*nscale+.5;ctx.beginPath();ctx.moveTo(xx,ntop);ctx.lineTo(xx,ntop+S.neighbor_raster_height*nscale);ctx.stroke();
    }
    for(let y=0;y<=S.neighbor_raster_height;y++){
      const yy=ntop+y*nscale+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(S.neighbor_raster_width*nscale,yy);ctx.stroke();
    }
    ctx.restore();

    ctx.save();
    ctx.strokeStyle='rgba(190,25,25,.95)';ctx.lineWidth=2;
    for(const yy of [S.neighbor_core_top,S.neighbor_core_bottom]){
      const y=ntop+yy*nscale+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();
    }
    ctx.fillStyle='rgba(190,25,25,.95)';ctx.font='12px monospace';ctx.textBaseline='bottom';
    ctx.fillText('målrad '+S.neighbor_core_top+'..'+S.neighbor_core_bottom+' px',4,ntop-3);
    ctx.restore();
  }
  checkbox.addEventListener('change',()=>{wrap.style.display=checkbox.checked?'block':'none';if(checkbox.checked)drawNeighbor();});
  nimg.onload=()=>{if(checkbox.checked)drawNeighbor();};
})();
</script>
'''.replace("__DIAGNOSTICS__", diag_json)
    return document.replace('</body>', script + '</body>', 1)


fast.ui.editor.render_html = render_html_with_neighbor_raster

# Remember the actual row being edited for the lifetime of one POST request.
# ThreadingHTTPServer uses a request thread, so thread-local state avoids one
# browser request affecting another concurrent request.
_post_context = threading.local()


def apply_edit_on_active_row(state, facit, form):
    position = (int(state["column"]), int(state["row"]))
    _post_context.active_position = position
    action = (form.get("action") or [""])[0]
    try:
        return apply_edit_with_delete(_original_apply_edit, state, facit, form)
    except Exception as exc:
        print(
            f"review: SPARFEL kolumn {position[0]}, rad {position[1]}, "
            f"action={action!r}: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise


fast.legacy.apply_edit = apply_edit_on_active_row

# In defect mode the URL can still point at the scan anchor while the editor is
# actually displaying the first defective row found much later on the page.
# The base editor's form has no explicit action, so the browser would POST back
# to that stale anchor row. Make the form submit to the row that is actually
# active in the editor, preserving defect mode and the packet anchor.
_original_five_row_render = fast.ui.render_five_row_html
_original_row_url = fast.ui.row_url


def row_url_preserving_failed_post(position, *, mode="all", anchor=None, scan="forward"):
    active = getattr(_post_context, "active_position", None)
    if active is not None:
        if position == active:
            # Normal success redirect: the base handler is already returning to
            # the edited row, so consume the request-local marker and preserve
            # its mode/anchor exactly.
            del _post_context.active_position
        else:
            # The base handler only asks for another position after an exception
            # (historically the command-line start row). Never throw the user
            # away from the row whose edit failed. Use all-mode so the row stays
            # visible even if the facit file was partly changed before failure.
            del _post_context.active_position
            print(
                f"review: sparfel: behåller kolumn {active[0]}, rad {active[1]} "
                f"i stället för fallback kolumn {position[0]}, rad {position[1]}",
                flush=True,
            )
            return _original_row_url(active)
    return _original_row_url(position, mode=mode, anchor=anchor, scan=scan)


fast.ui.row_url = row_url_preserving_failed_post


def render_five_row_html_to_active_row(
    states,
    active_position,
    all_positions,
    message="",
    *,
    mode="all",
    anchor=None,
):
    document = _original_five_row_render(
        states,
        active_position,
        all_positions,
        message,
        mode=mode,
        anchor=anchor,
    )
    packet_anchor = anchor or (states[0]["column"], states[0]["row"])
    action = fast.ui.row_url(active_position, mode=mode, anchor=packet_anchor)
    needle = '<form method="post" id="form">'
    replacement = (
        '<form method="post" id="form" action="'
        + html.escape(action, quote=True)
        + '">'
    )
    if needle not in document:
        raise ValueError("could not find glyph edit form in five-row editor HTML")
    return document.replace(needle, replacement, 1)


fast.ui.render_five_row_html = render_five_row_html_to_active_row


def main() -> int:
    print("review: ULTRAFAST använder grupperad exact-glyphmatchning vid säkra vita gap", flush=True)
    print("review: två-rads-ägarskap delar bara komponenter som exakt förklaras av kända glypher på båda baselines", flush=True)
    print("review: vald matchad glyph kan raderas ur facit för att delas om", flush=True)
    print("review: glyphändringar POST:as alltid till den faktiskt aktiva raden", flush=True)
    print("review: sparfel stannar på aktiv rad och skrivs ut i terminalen", flush=True)
    print("review: Visa grannrader visar ofiltrerat raster ±8 px runt målradens gränser", flush=True)
    print("review: Kopiera diagnostik ger ett textblock som kan klistras direkt i ChatGPT", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
