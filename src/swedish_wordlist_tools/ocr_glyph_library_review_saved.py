from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


_EXTRA_STYLE = """
<style>
#exportboxes{font:inherit;padding:.45rem .7rem;margin-left:.5rem;cursor:pointer}
.review.saved{background:#e8f6e8;border-color:#398439}
</style>
"""

_EXTRA_SCRIPT = r"""
<script>
const SAOL_OVERRIDE_KEY='saol14-glyph-box-overrides-v1';
function loadOverrides(){try{return JSON.parse(localStorage.getItem(SAOL_OVERRIDE_KEY)||'{}')}catch(_){return {}}}
function saveOverrides(v){localStorage.setItem(SAOL_OVERRIDE_KEY,JSON.stringify(v))}
function overrideKey(p){return p.style+'/'+p.filename}
function manualColumnBox(){if(!payload||!manual)return null;return [payload.origin[0]+manual[0],payload.origin[1]+manual[1],manual[2],manual[3]]}
function markSavedButtons(){const all=loadOverrides();document.querySelectorAll('.review').forEach(b=>{const p=JSON.parse(b.dataset.review);b.classList.toggle('saved',!!all[overrideKey(p)]);b.textContent=all[overrideKey(p)]?'granska / rita box ✓':'granska / rita box';});}

document.querySelectorAll('.review').forEach(b=>b.addEventListener('click',()=>{
  const all=loadOverrides(), saved=all[overrideKey(payload)];
  if(saved&&Array.isArray(saved.bbox)) manual=[saved.bbox[0]-payload.origin[0],saved.bbox[1]-payload.origin[1],saved.bbox[2],saved.bbox[3]];
}));
canvas.addEventListener('pointerup',()=>{
  if(!payload||!manual)return;
  const all=loadOverrides();
  all[overrideKey(payload)]={filename:payload.filename,page:payload.page,column:payload.column,bbox:manualColumnBox(),label:payload.label,style:payload.style};
  saveOverrides(all);markSavedButtons();showCoords();
});
document.getElementById('resetbox').addEventListener('click',()=>{
  if(!payload)return;const all=loadOverrides();delete all[overrideKey(payload)];saveOverrides(all);markSavedButtons();
});
document.getElementById('copybox').textContent='kopiera manuell box';
document.getElementById('exportboxes').addEventListener('click',()=>{
  const data=JSON.stringify({version:1,overrides:loadOverrides()},null,2)+'\n';
  const blob=new Blob([data],{type:'application/json'}),a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='saol14-glyph-box-overrides.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
});
markSavedButtons();
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SAOL glyph review HTML with persistent manual bbox overrides.")
    parser.add_argument("library", type=Path)
    parser.add_argument("--style", choices=("italic", "bold", "roman"))
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "swedish_wordlist_tools.ocr_glyph_library_review", str(args.library), "--out", str(args.out), "--scale", str(args.scale)]
    if args.style:
        cmd += ["--style", args.style]
    if args.jsonl:
        cmd += ["--jsonl", str(args.jsonl)]
    subprocess.run(cmd, check=True)

    doc = args.out.read_text(encoding="utf-8")
    doc = doc.replace('</style>', '</style>'+_EXTRA_STYLE, 1)
    doc = doc.replace('</div>\n'+doc[doc.find("{''.join(style_sections)}"):] if False else '<div class="toolbar"><input id="filter" placeholder="Filtrera tecken, stil eller filnamn…"></div>', '<div class="toolbar"><input id="filter" placeholder="Filtrera tecken, stil eller filnamn…"><button id="exportboxes">exportera sparade boxar</button></div>', 1)
    doc += _EXTRA_SCRIPT
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print("manual_box_storage=localStorage export=saol14-glyph-box-overrides.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
