from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v12 as v12


def main() -> int:
    """Generate v12 and add an independent hidden style-copy for every card.

    A row can contain an italic form followed by a roman explanation (or vice
    versa).  The user can reveal a second copy of the exact same raster and mark
    that copy with another style.  The copy starts with no proposals so evidence
    from the first style is never silently carried across.
    """
    rc = v12.main()
    if rc:
        return rc

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale")
    ap.add_argument("--margin")
    ap.add_argument("--ink-threshold")
    args, _ = ap.parse_known_args(sys.argv[1:])

    text = args.out.read_text(encoding="utf-8")

    # Give every ordinary card a reveal button.  The duplicate is present before
    # JS initialization, so it receives the exact same editor handlers/state as
    # every other card; it is merely hidden until requested.
    button_anchor = '<button class="clear" type="button">Rensa ordet</button>'
    button_repl = button_anchor + '<button class="stylecopy-show" type="button">Kopiera rad för annan stil</button>'
    if button_anchor not in text:
        raise SystemExit("could not add style-copy button")
    text = text.replace(button_anchor, button_repl)

    card_re = re.compile(r'(<article class="card"\n.*?</article>)', re.S)
    cards = card_re.findall(text)
    if not cards:
        raise SystemExit("could not find cards for style copies")

    for original in cards:
        # The primary keeps its button.  The hidden copy has independent state,
        # starts blank, and gets a distinct atlas source id so merge retains both
        # style-specific pieces of evidence from the same printed row.
        copy = original.replace('<article class="card"\n', '<article class="card style-copy" style="display:none"\n', 1)
        m = re.search(r'data-source-id="([^"]*)"', copy)
        sid = html.unescape(m.group(1)) if m else ""
        copy = re.sub(r'data-source-id="[^"]*"', 'data-source-id="' + html.escape(sid + '::stylecopy', quote=True) + '"', copy, count=1)
        copy = re.sub(r"data-proposals='[^']*'", "data-proposals='[]'", copy, count=1)
        copy = copy.replace('Kopiera rad för annan stil</button>', 'Dölj stilkopia</button>', 1)
        text = text.replace(original, original + copy, 1)

    # After all cards have been initialized, wire the primary/copy pairs.  Using
    # the existing style selector's onchange means style-dependent auto proposals,
    # baseline voting and live propagation all follow the selected style.
    script_anchor = "document.querySelector('#export').onclick=()=>{"
    helper = r'''
for(const primary of document.querySelectorAll('.card:not(.style-copy)')){
 const copy=primary.nextElementSibling;
 if(!copy || !copy.classList.contains('style-copy'))continue;
 const show=primary.querySelector('.stylecopy-show');
 const hide=copy.querySelector('.stylecopy-show');
 show.onclick=()=>{
   copy.style.display='block';
   const a=primary.querySelector('.style-select').value;
   const b=copy.querySelector('.style-select');
   // Pick the most useful opposite style automatically; user can still choose
   // italic/roman/bold explicitly afterwards.
   b.value=(a==='italic'?'roman':'italic');
   b.onchange();
   copy.scrollIntoView({behavior:'smooth',block:'center'});
 };
 hide.onclick=()=>{copy.style.display='none';};
}
'''
    if script_anchor not in text:
        raise SystemExit("could not install style-copy handlers")
    text = text.replace(script_anchor, helper + "\n" + script_anchor, 1)

    # Hidden unused copies must not pollute the export.  A revealed copy is real
    # evidence even if the user later scrolls away from it.
    export_loop = "for(const [card,proposals,state,INK] of allCards){"
    export_repl = export_loop + "\n  if(card.classList.contains('style-copy') && card.style.display==='none')continue;"
    if export_loop not in text:
        raise SystemExit("could not patch export for hidden style copies")
    text = text.replace(export_loop, export_repl, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v12</h1>",
        "<h1>SAOL live-lärande pixelannotering v13</h1>",
        1,
    )
    text = text.replace(
        "<p><b>Stil per rad:</b>",
        "<p><b>Blandad stil på samma tryckrad:</b> klicka <i>Kopiera rad för annan stil</i> för en oberoende kopia av samma raster. Kopian börjar utan annotationer och föreslår automatiskt motsatt roman/kursiv stil; välj även fet om det behövs. Märk bara den del som hör till den andra stilen. <b>Stil per rad:</b>",
        1,
    )
    text = text.replace("corrected-v12", "corrected-v13")
    text = text.replace("corrected-v12.json", "corrected-v13.json")

    args.out.write_text(text, encoding="utf-8")
    print(f"v13: {len(cards)} hidden independent style-copy rows available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
