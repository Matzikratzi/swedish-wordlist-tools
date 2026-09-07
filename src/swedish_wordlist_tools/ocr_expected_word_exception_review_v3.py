from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v13 as v13


def main() -> int:
    ap0 = argparse.ArgumentParser(add_help=False)
    ap0.add_argument("decode", type=Path)
    ap0.add_argument("library")
    ap0.add_argument("--out", type=Path, required=True)
    ap0.add_argument("--min-orphan", type=int, default=6)
    ap0.add_argument("--scale")
    ap0.add_argument("--margin")
    ap0.add_argument("--ink-threshold")
    args, _ = ap0.parse_known_args(sys.argv[1:])

    payload = json.loads(args.decode.read_text(encoding="utf-8"))
    fmt = str(payload.get("format") or "")
    if fmt not in {"saol-expected-word-decode-v1", "saol-expected-word-decode-v2"}:
        raise SystemExit(f"expected constrained decode input, got {fmt!r}")

    rows = list(payload.get("results") or [])
    kept=[]; hidden=0
    for row in rows:
        missing=list(row.get("decode_missing_labels") or [])
        orphan=int(row.get("decode_orphan_residual_pixels", row.get("decode_unexplained_pixels",0)) or 0)
        if missing or orphan>=args.min_orphan: kept.append(row)
        else: hidden+=1
    kept.sort(key=lambda r:(
        0 if (r.get("decode_missing_labels") or []) else 1,
        -len(r.get("decode_missing_labels") or []),
        -int(r.get("decode_orphan_residual_pixels",r.get("decode_unexplained_pixels",0)) or 0),
        str(r.get("expected_word") or ""),
    ))
    filtered=dict(payload); filtered["results"]=kept; filtered["exception_word_count"]=len(kept)
    filtered["review_hidden_small_residual_count"]=hidden; filtered["review_min_orphan"]=args.min_orphan

    tmp=args.decode.with_name(args.decode.stem+".review-v3-filtered.json")
    tmp.write_text(json.dumps(filtered,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    old=sys.argv[:]
    try:
        sys.argv[1]=str(tmp)
        cleaned=[sys.argv[0]]; skip=False
        for token in sys.argv[1:]:
            if skip: skip=False; continue
            if token=="--min-orphan": skip=True; continue
            if token.startswith("--min-orphan="): continue
            cleaned.append(token)
        sys.argv=cleaned
        rc=v13.main()
    finally:
        sys.argv=old
        try: tmp.unlink()
        except OSError: pass
    if rc: return rc

    text=args.out.read_text(encoding="utf-8")
    text=text.replace("<h1>SAOL live-lärande pixelannotering v13</h1>","<h1>SAOL undantagsgranskning v3 – saknat facit först + blandad stil</h1>",1)
    intro=(f"<p><b>Prioriterad constrained review:</b> {payload.get('resolved_word_count',0)} ord var redan helt bevisade. "
           f"Av {len(rows)} decoder-undantag visas {len(kept)}; {hidden} små residualfall doldes. "
           "Om kursiv text övergår i roman på samma tryckrad: använd <i>Kopiera rad för annan stil</i> och märk respektive del i varsin stilkopia.</p>")
    text=text.replace("</h1>","</h1>"+intro,1)
    for row in kept:
        expected=str(row.get("expected_word") or "")
        if not expected: continue
        missing=list(row.get("decode_missing_labels") or [])
        orphan=int(row.get("decode_orphan_residual_pixels",row.get("decode_unexplained_pixels",0)) or 0)
        attached=int(row.get("decode_attached_residual_pixels",0) or 0)
        bits=[]
        if missing: bits.append("SAKNAR FACIT: "+" ".join(map(str,missing)))
        if orphan: bits.append(f"fristående restbläck: {orphan} px")
        if attached: bits.append(f"anslutet restbläck: {attached} px")
        needle=f">{expected}<"; repl=f">{expected}<span class=\"decode-reason\" style=\"margin-left:.7em;color:#9b3d00;font-weight:600\">[{'; '.join(bits)}]</span><"
        text=text.replace(needle,repl,1)
    text=text.replace("corrected-v13","expected-exceptions-corrected-v15")
    text=text.replace("corrected-v13.json","expected-exceptions-corrected-v15.json")
    args.out.write_text(text,encoding="utf-8")
    print(f"exception review v3: cards={len(kept)}; hidden-small-residual={hidden}; mixed-style copies enabled")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
