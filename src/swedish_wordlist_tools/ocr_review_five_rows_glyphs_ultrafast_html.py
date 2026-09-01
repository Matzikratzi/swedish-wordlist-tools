from __future__ import annotations

import html
import threading

from . import ocr_review_five_rows_glyphs_fast_html as fast
from .ocr_glyph_review_delete import apply_edit_with_delete, render_html_with_delete
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


# The fast editor already reuses page geometry, keeps generation-aware row
# state, and prevents duplicate concurrent work. Its remaining hot path is the
# whole-row exact matcher imported into that module as ``analyse_row_exact``.
# Swap only that implementation for the previously verified safe-gap grouped
# matcher. ``load_review_state_fast`` resolves the module global at call time,
# so no other editor behaviour changes.
fast.analyse_row_exact = analyse_row_exact_grouped

# Add an unfiltered narrow source raster around the target row. This is
# diagnostic only: matching still uses the conservative owned-row crop.
_original_load_review_state_fast = fast.load_review_state_fast


def load_review_state_with_neighbors(context, position, models):
    state = _original_load_review_state_fast(context, position, models)
    return add_neighbor_row_raster(context, state, probe_y=8)


fast.load_review_state_fast = load_review_state_with_neighbors

# Add a narrowly scoped destructive action to the same editor. Keep references
# to the original renderer and edit handler before monkeypatching so wrappers
# cannot recurse.
_original_render_html = fast.ui.editor.render_html
_original_apply_edit = fast.legacy.apply_edit


def render_html_with_neighbor_raster(state, message=""):
    document = render_html_with_delete(_original_render_html, state, message)
    if not state.get("neighbor_raster_image"):
        return document

    controls_needle = '<span id="pixelCount">0 valda pixlar</span>\n</div>'
    controls_replacement = (
        '<span id="pixelCount">0 valda pixlar</span>\n'
        '<label class="inline"><input type="checkbox" id="showNeighbors"> Visa grannrader</label>\n'
        '</div>'
    )
    if controls_needle not in document:
        raise ValueError("could not find editor controls for neighbor raster")
    document = document.replace(controls_needle, controls_replacement, 1)

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
'''
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
    print("review: vald matchad glyph kan raderas ur facit för att delas om", flush=True)
    print("review: glyphändringar POST:as alltid till den faktiskt aktiva raden", flush=True)
    print("review: sparfel stannar på aktiv rad och skrivs ut i terminalen", flush=True)
    print("review: Visa grannrader visar ofiltrerat raster ±8 px runt målradens gränser", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
