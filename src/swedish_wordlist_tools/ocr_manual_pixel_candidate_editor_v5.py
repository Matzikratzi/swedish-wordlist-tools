from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v4 as v4


def main() -> int:
    # v5 deliberately reuses the stable DOM-grid/box/pixel implementation from
    # v4 and only changes the annotation-entry interaction in the generated HTML.
    rc = v4.main()
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

    old_handler = "card.querySelector('.label').onchange=e=>{if(state.selected===null)return;proposals[state.selected].label=e.target.value.trim();render()};"
    new_handler = """const labelInput=card.querySelector('.label');
 function startNewLabel(){
   const label=labelInput.value.trim();
   if(!label)return;
   proposals.push({label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});
   state.selected=proposals.length-1;
   labelInput.value='';
   render();
 }
 labelInput.onchange=startNewLabel;
 labelInput.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();startNewLabel();}};"""
    if old_handler not in text:
        raise SystemExit("could not patch v4 label handler")
    text = text.replace(old_handler, new_handler, 1)

    old_select = "card.querySelector('.label').value=proposals[state.selected].label;render();"
    new_select = "card.querySelector('.label').value='';render();"
    text = text.replace(old_select, new_select)

    # The explicit New button is redundant in the new loop; keep the underlying
    # code harmlessly present but hide the control.
    text = text.replace(
        '<button class="new" type="button">Nytt förslag</button>',
        '<button class="new" type="button" style="display:none">Nytt förslag</button>',
    )

    text = text.replace(
        "<h1>SAOL autoannotering → manuell korrigering v4</h1>",
        "<h1>SAOL autoannotering → manuell korrigering v5</h1>",
    )
    text = text.replace(
        "<p><b>Boxläge:</b>",
        "<p><b>Arbetsflöde:</b> skriv en etikett (Enter eller klicka vidare) → en ny separat annotation skapas alltid. Märk den sedan med box eller pixlar. Upprepa. Överlapp mellan annotationer är tillåtet. <b>Boxläge:</b>",
        1,
    )
    text = text.replace("corrected-v4", "corrected-v5")
    text = text.replace("corrected-v4.json", "corrected-v5.json")

    args.out.write_text(text, encoding="utf-8")
    print("v5 interaction: label entry always starts a new annotation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
