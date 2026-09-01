from __future__ import annotations

import html
import json
import threading

from . import ocr_review_five_rows_glyphs_fast_html as fast
from .ocr_glyph_review_delete import apply_edit_with_delete, render_html_with_delete
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped
from .ocr_two_row_glyph_ownership import split_touching_neighbor_glyphs


fast.analyse_row_exact = analyse_row_exact_grouped

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

_original_render_html = fast.ui.editor.render_html
_original_apply_edit = fast.legacy.apply_edit


def diagnostic_text(state: dict) -> str:
    """Return paste-friendly metadata plus the complete three-row pixel raster."""
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
                "three_row_raster:",
                f"  size={state.get('neighbor_raster_width')}x{state.get('neighbor_raster_height')}",
                f"  page_y={state.get('neighbor_page_top')}..{state.get('neighbor_page_bottom')}",
                f"  target_core_y={state.get('neighbor_core_top')}..{state.get('neighbor_core_bottom')}",
                f"  boundaries={state.get('neighbor_row_boundaries')}",
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
    raster = state.get("neighbor_raster_ascii")
    if raster:
        lines.extend(["three_row_raster_ascii:", str(raster)])
    return "\n".join(lines) + "\n"


def render_html_with_neighbor_raster(state, message=""):
    document = render_html_with_delete(_original_render_html, state, message)

    diagnostics = diagnostic_text(state)
    diag_json = json.dumps(diagnostics, ensure_ascii=False).replace("</", "<\\/")
    controls_needle = '<span id="pixelCount">0 valda pixlar</span>\n</div>'
    controls = '<span id="pixelCount">0 valda pixlar</span>\n'
    if state.get("neighbor_raster_image"):
        controls += '<label class="inline"><input type="checkbox" id="showNeighbors"> Visa tre rader</label>\n'
    controls += '<button type="button" id="copyDiagnostics">Kopiera diagnostik + raster</button>\n</div>'
    if controls_needle not in document:
        raise ValueError("could not find editor controls for diagnostics")
    document = document.replace(controls_needle, controls, 1)

    if state.get("neighbor_raster_image"):
        rowbox_needle = '<div class="rowbox"><canvas id="row"></canvas></div>'
        neighbor_box = rowbox_needle + '''
<div id="neighborWrap" style="display:none;margin:10px 0 18px">
  <div><b>Tre-radersraster</b> – ofiltrerad källa: föregående rad, målrad och nästa rad.</div>
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
      setTimeout(()=>copyButton.textContent='Kopiera diagnostik + raster',1200);
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

    ctx.save();ctx.strokeStyle='rgba(70,70,70,.22)';ctx.lineWidth=1;
    for(let x=0;x<=S.neighbor_raster_width;x++){
      const xx=x*nscale+.5;ctx.beginPath();ctx.moveTo(xx,ntop);ctx.lineTo(xx,ntop+S.neighbor_raster_height*nscale);ctx.stroke();
    }
    for(let y=0;y<=S.neighbor_raster_height;y++){
      const yy=ntop+y*nscale+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(S.neighbor_raster_width*nscale,yy);ctx.stroke();
    }
    ctx.restore();

    ctx.save();ctx.strokeStyle='rgba(190,25,25,.95)';ctx.lineWidth=2;
    const boundaries=S.neighbor_row_boundaries || [[S.neighbor_core_top,'target top'],[S.neighbor_core_bottom,'target bottom']];
    for(const entry of boundaries){
      const yy=entry[0], label=entry[1];
      const y=ntop+yy*nscale+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();
      ctx.fillStyle='rgba(190,25,25,.95)';ctx.font='11px monospace';ctx.fillText(label,4,Math.max(11,y-2));
    }
    ctx.restore();
  }
  checkbox.addEventListener('change',()=>{wrap.style.display=checkbox.checked?'block':'none';if(checkbox.checked)drawNeighbor();});
  nimg.onload=()=>{if(checkbox.checked)drawNeighbor();};
})();
</script>
'''.replace("__DIAGNOSTICS__", diag_json)
    return document.replace('</body>', script + '</body>', 1)


fast.ui.editor.render_html = render_html_with_neighbor_raster

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

_original_five_row_render = fast.ui.render_five_row_html
_original_row_url = fast.ui.row_url


def row_url_preserving_failed_post(position, *, mode="all", anchor=None, scan="forward"):
    active = getattr(_post_context, "active_position", None)
    if active is not None:
        if position == active:
            del _post_context.active_position
        else:
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
    print("review: två-radsdelning kräver exact glyphbevis och bevarad vertikal radordning", flush=True)
    print("review: glyphändringar POST:as alltid till den faktiskt aktiva raden", flush=True)
    print("review: sparfel stannar på aktiv rad och skrivs ut i terminalen", flush=True)
    print("review: Visa tre rader visar hela föregående/mål/nästa fysiska rad", flush=True)
    print("review: Kopiera diagnostik + raster ger #/. för hela tre-radersfältet", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
