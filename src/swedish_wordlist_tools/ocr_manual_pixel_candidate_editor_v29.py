from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v28 as v28


def _pixel_key(pixels: object) -> tuple[tuple[int, int], ...]:
    if not isinstance(pixels, list):
        return ()
    pts = []
    for p in pixels:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            pts.append((int(p[0]), int(p[1])))
    return tuple(sorted(pts))


def _style_index(payload: dict[str, object]) -> dict[str, dict[tuple[str, tuple[tuple[int, int], ...]], str]]:
    index: dict[str, dict[tuple[str, tuple[tuple[int, int], ...]], str]] = {}
    words = payload.get("words")
    if isinstance(words, list):
        for word in words:
            if not isinstance(word, dict):
                continue
            sid = str(word.get("source_id") or "")
            wf = str(word.get("word_file") or "")
            default = str(word.get("style") or "roman")
            m: dict[tuple[str, tuple[tuple[int, int], ...]], str] = {}
            for ann in word.get("annotations", []):
                if not isinstance(ann, dict):
                    continue
                label = str(ann.get("label") or "")
                key = _pixel_key(ann.get("pixels"))
                if label and key:
                    m[(label, key)] = str(ann.get("style") or default)
            if sid:
                index[sid] = m
            if wf:
                index["wf:" + wf] = m
    results = payload.get("results")
    if isinstance(results, list):
        for word in results:
            if not isinstance(word, dict):
                continue
            sid = str(word.get("source_id") or "")
            wf = str(word.get("word_file") or "")
            default = str(word.get("style") or "roman")
            m: dict[tuple[str, tuple[tuple[int, int], ...]], str] = {}
            for bucket in ("matches", "rejected_candidates"):
                obj = word.get(bucket) or {}
                if not isinstance(obj, dict):
                    continue
                for label, hits in obj.items():
                    if not isinstance(hits, list):
                        continue
                    for hit in hits:
                        if not isinstance(hit, dict):
                            continue
                        key = _pixel_key(hit.get("matched_pixels"))
                        if key:
                            m[(str(label), key)] = str(hit.get("style") or default)
            if sid:
                index[sid] = m
            if wf:
                index["wf:" + wf] = m
    return index


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit("usage: ...v29 INPUT LIBRARY --out FILE")
    source = Path(argv[0])
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])
    rc = v28.main()
    if rc or out is None or not out.exists():
        return rc

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"v29: cannot read input for style restoration: {exc}")
    idx = _style_index(payload)
    text = out.read_text(encoding="utf-8")

    card_re = re.compile(
        r"(<article class=\"card\"\s+)(.*?)(data-proposals=')([^']*)('>)",
        re.S,
    )
    patched = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal patched
        attrs = match.group(2)
        sid_m = re.search(r'data-source-id="([^"]*)"', attrs)
        wf_m = re.search(r'data-word-file="([^"]*)"', attrs)
        sid = html.unescape(sid_m.group(1)) if sid_m else ""
        wf = html.unescape(wf_m.group(1)) if wf_m else ""
        styles = idx.get(sid) or idx.get("wf:" + wf) or {}
        try:
            proposals = json.loads(html.unescape(match.group(4)))
        except Exception:
            return match.group(0)
        changed = False
        for p in proposals:
            if not isinstance(p, dict):
                continue
            key = (str(p.get("label") or ""), _pixel_key(p.get("pixels")))
            st = styles.get(key)
            if st:
                p["style"] = st
                changed = True
        if not changed:
            return match.group(0)
        patched += 1
        encoded = html.escape(json.dumps(proposals, ensure_ascii=False), quote=True)
        return match.group(1) + attrs + match.group(3) + encoded + match.group(5)

    text = card_re.sub(repl, text)
    text = text.replace("SAOL live-lärande pixelannotering v28", "SAOL live-lärande pixelannotering v29", 1)
    text = text.replace("corrected-v28.json", "corrected-v29.json")
    text = text.replace(
        "<b>En rad per raster:</b>",
        "<b>Bevarad stil från facit:</b> återupptagna och förberäknade kandidater behåller nu sin egen roman/kursiv/fet-stil även när flera stilar finns på samma rad. <b>En rad per raster:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print(f"v29: restored per-proposal style on {patched} cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
