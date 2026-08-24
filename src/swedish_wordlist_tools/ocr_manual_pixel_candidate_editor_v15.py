from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v14 as v14


def main() -> int:
    rc = v14.main()
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

    # Export becomes async so the exact same JSON can first be persisted by the
    # local review server and then downloaded as before.  A failed server save
    # never prevents the local download; the browser reports the failure visibly.
    old_handler = "document.querySelector('#export').onclick=()=>{"
    new_handler = "document.querySelector('#export').onclick=async()=>{"
    if old_handler not in text:
        raise SystemExit("could not patch v15 async export handler")
    text = text.replace(old_handler, new_handler, 1)

    blob_anchor = "const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{type:'application/json'}),a=document.createElement('a');"
    server_save = r'''const exportText=JSON.stringify(out,null,2)+'\n';
 let saveMessage='';
 try{
   const response=await fetch('/api/save-atlas',{method:'POST',headers:{'Content-Type':'application/json'},body:exportText});
   const result=await response.json();
   if(!response.ok || !result.ok)throw new Error(result.error||('HTTP '+response.status));
   saveMessage='Server: '+result.version_file+' · '+result.word_count+' ord';
 }catch(err){
   saveMessage='SERVERSPARNING MISSLYCKADES: '+err;
 }
 let status=document.querySelector('#server-save-status');
 if(status)status.textContent=saveMessage;
 const blob=new Blob([exportText],{type:'application/json'}),a=document.createElement('a');'''
    if blob_anchor not in text:
        raise SystemExit("could not patch v15 export blob")
    text = text.replace(blob_anchor, server_save, 1)

    toolbar = '<div class="toolbar"><button id="export">Exportera korrigerad atlas</button></div>'
    toolbar_new = '<div class="toolbar"><button id="export">Exportera + spara version på servern</button> <span id="server-save-status" style="font-size:12px;font-weight:600"></span></div>'
    if toolbar not in text:
        raise SystemExit("could not patch v15 export toolbar")
    text = text.replace(toolbar, toolbar_new, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v14</h1>",
        "<h1>SAOL live-lärande pixelannotering v15</h1>",
        1,
    )
    text = text.replace(
        "<p><b>Snabb glyphgranskning:</b>",
        "<p><b>Versionssäker export:</b> exportknappen skickar samma atlas-JSON till review-servern, som sparar en oföränderlig versionsfil och uppdaterar latest.json; därefter laddas filen även ner lokalt. Om serverdelen misslyckas fortsätter den lokala nedladdningen och felet visas bredvid knappen. <b>Snabb glyphgranskning:</b>",
        1,
    )
    text = text.replace("corrected-v14", "corrected-v15")
    text = text.replace("corrected-v14.json", "corrected-v15.json")

    args.out.write_text(text, encoding="utf-8")
    print("v15: export persists immutable server version + latest.json and still downloads locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
