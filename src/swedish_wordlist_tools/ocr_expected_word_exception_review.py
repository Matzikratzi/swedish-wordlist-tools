from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v12 as v12


def main() -> int:
    ap0 = argparse.ArgumentParser(add_help=False)
    ap0.add_argument("decode", type=Path)
    ap0.add_argument("library")
    ap0.add_argument("--out", type=Path, required=True)
    ap0.add_argument("--scale")
    ap0.add_argument("--margin")
    ap0.add_argument("--ink-threshold")
    args, _ = ap0.parse_known_args(sys.argv[1:])

    payload = json.loads(args.decode.read_text(encoding="utf-8"))
    if payload.get("format") != "saol-expected-word-decode-v1":
        raise SystemExit("expected saol-expected-word-decode-v1 input")

    # v12 consumes the same transfer-shaped result rows; run it unchanged first.
    rc = v12.main()
    if rc:
        return rc

    text = args.out.read_text(encoding="utf-8")
    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v12</h1>",
        "<h1>SAOL undantagsgranskning – bara det decodern inte kan bevisa</h1>",
        1,
    )

    intro = (
        f"<p><b>Constrained decoding:</b> {payload.get('resolved_word_count', 0)} nya ord kunde förklaras helt och visas inte. "
        f"{payload.get('exception_word_count', len(payload.get('results', [])))} ord behöver granskning. "
        "Textsträngen är känd i förväg; sidan visar bara fall där någon förväntad glyph/kluster saknas eller där bläck blir oförklarat. "
        "Rätta med samma etikett → box/pixel-flöde som tidigare. Exporten innehåller bara dessa undantag; slå sedan ihop den med föregående atlas med ocr_merge_manual_pixel_atlases.</p>"
    )
    marker = "</h1>"
    if marker in text:
        text = text.replace(marker, marker + intro, 1)

    for row in payload.get("results", []):
        expected = str(row.get("expected_word") or "")
        if not expected:
            continue
        missing = row.get("decode_missing_labels") or []
        unexpl = int(row.get("decode_unexplained_pixels") or 0)
        changed = bool(row.get("style_changed"))
        bits = []
        if missing:
            bits.append("saknar: " + " ".join(str(x) for x in missing))
        if unexpl:
            bits.append(f"oförklarat bläck: {unexpl} px")
        if changed:
            bits.append("stil ändrad av decodern")
        if not bits:
            bits.append("tveksam helordstolkning")
        needle = f">{expected}<"
        repl = f">{expected}<span class=\"decode-reason\" style=\"margin-left:.7em;color:#9b3d00;font-weight:600\">[{'; '.join(bits)}]</span><"
        text = text.replace(needle, repl, 1)

    text = text.replace("corrected-v12", "expected-exceptions-corrected-v13")
    text = text.replace("corrected-v12.json", "expected-exceptions-corrected-v13.json")
    args.out.write_text(text, encoding="utf-8")
    print(f"exception review: {payload.get('exception_word_count', 0)} cards; {payload.get('resolved_word_count', 0)} resolved words hidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
