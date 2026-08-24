from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v16 as v16


def _atlas_as_matches(path: Path) -> tuple[Path | None, dict[str, object] | None, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, 0
    if not str(payload.get("format") or "").startswith("saol-manual-pixel-atlas-corrected-"):
        return None, None, 0

    results = []
    dropped_middle_dot = 0
    for word in payload.get("words", []):
        if not isinstance(word, dict):
            continue
        matches: dict[str, list[dict[str, object]]] = {}
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            label = str(ann.get("label") or "")
            # Policy reset: every historical middle-dot annotation is invalid.
            # From now on · is relearned only as the true half-height separator;
            # the hanging heavy blob is labelled ¤.
            if label == "·":
                dropped_middle_dot += 1
                continue
            pixels = ann.get("pixels")
            if not label or not isinstance(pixels, list) or not pixels:
                continue
            matches.setdefault(label, []).append({
                "matched_pixels": pixels,
                "external_contact_pixels": [],
                "external_contacts": 0,
                "missing": 0,
                "extra": 0,
            })
        if not matches:
            continue
        results.append({
            "source_id": word.get("source_id"),
            "style": word.get("style"),
            "expected_word": word.get("expected_word"),
            "headword": word.get("headword"),
            "page": word.get("page"),
            "subnr": word.get("subnr"),
            "word_file": word.get("word_file"),
            "width": word.get("width"),
            "height": word.get("height"),
            "baseline_y": word.get("baseline_y"),
            "matches": matches,
            "rejected_candidates": {},
        })

    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix="-atlas-resume-matches.json", delete=False)
    with tmp:
        json.dump({"results": results}, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    progress = payload.get("review_progress") if isinstance(payload.get("review_progress"), dict) else None
    return Path(tmp.name), progress, dropped_middle_dot


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("matches", type=Path)
    pre.add_argument("library", type=Path)
    pre.add_argument("--out", type=Path, required=True)
    pre.add_argument("--scale")
    pre.add_argument("--margin")
    pre.add_argument("--ink-threshold")
    pre.add_argument("--examples-per-char")
    args, _ = pre.parse_known_args(sys.argv[1:])

    original_argv = sys.argv[:]
    converted, old_progress, dropped = _atlas_as_matches(args.matches)
    if converted is not None:
        sys.argv = original_argv[:]
        sys.argv[1] = str(converted)

    try:
        rc = v16.main()
    finally:
        sys.argv = original_argv
        if converted is not None:
            try:
                converted.unlink()
            except OSError:
                pass
    if rc:
        return rc

    if converted is None:
        print("v17: ordinary manifest/matches input; v16 behaviour unchanged")
        return 0

    text = args.out.read_text(encoding="utf-8")

    # Atlas entries are already user-reviewed truth.  v4 calls the matches bucket
    # 'accepted'; turn those restored proposals back into manual facit so they
    # participate as trusted learned glyphs rather than fresh OCR suggestions.
    old = "let proposals=JSON.parse(card.dataset.proposals).map((p,i)=>({...p,id:i,pixels:new Set((p.pixels||[]).map(q=>q[0]+','+q[1]))}));"
    new = "let proposals=JSON.parse(card.dataset.proposals).map((p,i)=>({...p,status:(p.status==='accepted'?'manual':p.status),id:i,pixels:new Set((p.pixels||[]).map(q=>q[0]+','+q[1]))}));"
    if old not in text:
        raise SystemExit("could not mark resumed atlas proposals as manual")
    text = text.replace(old, new, 1)

    if old_progress is not None:
        progress_json = json.dumps(old_progress, ensure_ascii=False)
        text = text.replace("let reviewStop=null;", f"let reviewStop={progress_json};", 1)
        restore = r'''
if(reviewStop){
 const cards=[...document.querySelectorAll('.card')];
 const card=cards.find(c=>c.dataset.sourceId===reviewStop.source_id) || cards.find(c=>c.dataset.wordFile===reviewStop.word_file);
 if(card){
   const btn=card.querySelector('.review-stop');if(btn){btn.textContent='HIT ✓';btn.style.fontWeight='800'}
   const status=document.querySelector('#review-stop-status');if(status)status.textContent='Tidigare granskat t.o.m. '+card.dataset.expected+' (sida '+card.dataset.page+')';
 }
}
'''
        anchor = "document.querySelector('#export').onclick=async()=>{"
        if anchor in text:
            text = text.replace(anchor, restore + "\n" + anchor, 1)

    text = text.replace("SAOL live-lärande pixelannotering v16", "SAOL live-lärande pixelannotering v17", 1)
    text = text.replace("corrected-v16.json", "corrected-v17.json")
    text = text.replace(
        "<p><b>Poängmatchning:</b>",
        "<p><b>Återupptagen atlas:</b> korrigerad atlas kan användas direkt som indata. Alla gamla `·` ignoreras medvetet; övriga annotationer återställs som manuellt facit. <b>Poängmatchning:</b>",
        1,
    )
    args.out.write_text(text, encoding="utf-8")
    print(f"v17: resumed corrected atlas; dropped_old_middle_dot={dropped}; review_progress={'yes' if old_progress else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
