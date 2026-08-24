from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image

from . import ocr_manual_pixel_candidate_editor_v14 as v14


def _manifest_as_matches(manifest: Path, library: Path, ink_threshold: int = 210) -> tuple[Path | None, dict[str, dict[str, object]]]:
    """Turn a mined glyph manifest into the word-match shape used by the pixel editor.

    The bold-headword miner already gives us one exact glyph crop plus its known
    character label and source metadata.  Treat the crop's dark pixels as one
    accepted initial proposal so the ordinary pixel editor can correct it just
    like an auto-matched word glyph.
    """
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, {}

    raw_sources = payload.get("template_sources")
    if not isinstance(raw_sources, dict) or not raw_sources:
        return None, {}

    results: list[dict[str, object]] = []
    sources: dict[str, dict[str, object]] = {}
    for rel, raw_meta in raw_sources.items():
        if not isinstance(rel, str) or not isinstance(raw_meta, dict):
            continue
        path = library / rel
        if not path.exists():
            continue
        try:
            with Image.open(path) as im0:
                im = im0.convert("L")
                width, height = im.size
                pixels = [
                    [x, y]
                    for y in range(height)
                    for x in range(width)
                    if im.getpixel((x, y)) < ink_threshold
                ]
        except OSError:
            continue

        label = str(raw_meta.get("character") or "")
        source_word = str(raw_meta.get("source_word") or raw_meta.get("expected_word") or label)
        results.append(
            {
                "source_id": f"manifest:{rel}",
                "style": str(raw_meta.get("style") or "bold"),
                "expected_word": label or source_word,
                "headword": source_word,
                "page": raw_meta.get("page") or 0,
                "subnr": str(raw_meta.get("subnr") or ""),
                "word_file": rel,
                "width": width,
                "height": height,
                # The crop is a single glyph.  Bottom ink is the safest initial
                # support-line guess; it remains fully editable in the UI.
                "baseline_y": max(0, max((p[1] for p in pixels), default=height - 1)),
                "matches": {
                    label: [
                        {
                            "matched_pixels": pixels,
                            "external_contact_pixels": [],
                            "external_contacts": 0,
                            "missing": 0,
                            "extra": 0,
                        }
                    ]
                }
                if label
                else {},
                "rejected_candidates": {},
            }
        )
        sources[rel] = raw_meta

    if not results:
        return None, sources

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix="-pixel-editor-matches.json", delete=False
    )
    with tmp:
        json.dump({"results": results}, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    return Path(tmp.name), sources


def _add_facsimile_links(text: str, sources: dict[str, dict[str, object]]) -> tuple[str, int]:
    links = 0
    for rel, meta in sources.items():
        source = meta.get("source")
        if not isinstance(source, str) or not source:
            continue
        page = meta.get("page") or ""
        source_word = meta.get("source_word") or meta.get("expected_word") or ""
        marker = f'data-word-file="{html.escape(rel, quote=True)}"'
        start = text.find(marker)
        if start < 0:
            continue
        header_end = text.find("</header>", start)
        if header_end < 0:
            continue
        link = (
            f'<a class="facsimile" href="{html.escape(source, quote=True)}" '
            f'target="_blank" rel="noopener">faksimil sida {html.escape(str(page))} ↗</a>'
        )
        if source_word:
            link += f'<span class="sourceword">{html.escape(str(source_word))}</span>'
        text = text[:header_end] + link + text[header_end:]
        links += 1
    if links:
        css_anchor = ".badge{font-size:11px;"
        css = ".facsimile{font-size:12px;font-weight:700;margin-left:auto}.sourceword{font-size:11px;color:#666}"
        pos = text.find(css_anchor)
        if pos >= 0:
            text = text[:pos] + css + text[pos:]
    return text, links


def main() -> int:
    # v15 can now take the bold harvest manifest directly as its first positional
    # argument.  Older match JSON remains completely unchanged.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("matches", type=Path)
    pre.add_argument("library", type=Path)
    pre.add_argument("--out", type=Path, required=True)
    pre.add_argument("--scale")
    pre.add_argument("--margin")
    pre.add_argument("--ink-threshold", type=int, default=210)
    args, _ = pre.parse_known_args(sys.argv[1:])

    original_argv = sys.argv[:]
    temp_matches: Path | None = None
    manifest_sources: dict[str, dict[str, object]] = {}
    converted, manifest_sources = _manifest_as_matches(
        args.matches, args.library, max(0, min(255, args.ink_threshold))
    )
    if converted is not None:
        temp_matches = converted
        rewritten = original_argv[:]
        # First positional argument is always argv[1] for this CLI family.
        rewritten[1] = str(converted)
        sys.argv = rewritten

    try:
        rc = v14.main()
    finally:
        sys.argv = original_argv
        if temp_matches is not None:
            try:
                temp_matches.unlink()
            except OSError:
                pass
    if rc:
        return rc

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

    facsimile_links = 0
    if manifest_sources:
        text, facsimile_links = _add_facsimile_links(text, manifest_sources)
        text = text.replace(
            "<p><b>Versionssäker export:</b>",
            "<p><b>Fet-skörd direkt:</b> första argumentet kan vara manifest-pages-bold-headwords.json. Varje skördad fet glyph öppnas då direkt i pixeleditorn med känt tecken förmarkerat och klickbar länk till rätt faksimilsida. <b>Versionssäker export:</b>",
            1,
        )

    args.out.write_text(text, encoding="utf-8")
    if manifest_sources:
        print(
            f"v15: opened bold harvest manifest with {len(manifest_sources)} source glyphs; "
            f"facsimile_links={facsimile_links}"
        )
    else:
        print("v15: export persists immutable server version + latest.json and still downloads locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
