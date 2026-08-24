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


def _manifest_as_matches(
    manifest: Path,
    library: Path,
    ink_threshold: int = 210,
    examples_per_char: int = 3,
) -> tuple[Path | None, dict[str, dict[str, object]]]:
    """Turn a harvest manifest into whole-word review cards.

    The page/word geometry is authoritative context.  We keep only a small
    number of glyph proposals per character, but always show the complete
    printed headword so baseline and neighbouring ink can be judged correctly.
    """
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, {}

    raw_sources = payload.get("template_sources")
    if not isinstance(raw_sources, dict) or not raw_sources:
        return None, {}

    groups: dict[tuple[object, ...], list[tuple[str, dict[str, object]]]] = {}
    for rel, meta in raw_sources.items():
        if not isinstance(rel, str) or not isinstance(meta, dict):
            continue
        wb = meta.get("page_word_bbox")
        if not isinstance(wb, (list, tuple)) or len(wb) != 4:
            continue
        key = (
            meta.get("page"), meta.get("subnr"), meta.get("source_word"),
            tuple(int(v) for v in wb), meta.get("style") or "bold",
        )
        groups.setdefault(key, []).append((rel, meta))

    if not groups:
        return None, raw_sources

    review_dir = library / "_pixel_editor_words"
    review_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    results: list[dict[str, object]] = []
    selected_sources: dict[str, dict[str, object]] = {}

    def group_sort(item):
        key, _items = item
        return (int(key[0] or 0), str(key[1] or ""), str(key[2] or ""))

    for key, items in sorted(groups.items(), key=group_sort):
        page, subnr, source_word, wb_tuple, style = key
        items.sort(key=lambda pair: int(pair[1].get("char_index") if pair[1].get("char_index") is not None else 9999))
        useful = [
            (rel, meta) for rel, meta in items
            if str(meta.get("character") or "") and counts.get(str(meta.get("character")), 0) < examples_per_char
        ]
        if not useful:
            continue
        page_image = Path(str(items[0][1].get("page_image") or ""))
        if not page_image.exists():
            continue
        wx, wy, ww, wh = map(int, wb_tuple)
        try:
            with Image.open(page_image) as im0:
                page_gray = im0.convert("L")
                word_im = page_gray.crop((wx, wy, wx + ww, wy + wh))
        except OSError:
            continue
        safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(source_word))[:60] or "word"
        word_rel = f"_pixel_editor_words/p{int(page or 0):05d}-sub{subnr}-{safe}.png"
        word_im.save(library / word_rel)

        matches: dict[str, list[dict[str, object]]] = {}
        for rel, meta in useful:
            label = str(meta.get("character") or "")
            if counts.get(label, 0) >= examples_per_char:
                continue
            pb = meta.get("page_bbox")
            if not isinstance(pb, (list, tuple)) or len(pb) != 4:
                continue
            gx, gy, gw, gh = map(int, pb)
            pixels = []
            for yy in range(max(wy, gy), min(wy + wh, gy + gh)):
                for xx in range(max(wx, gx), min(wx + ww, gx + gw)):
                    if page_gray.getpixel((xx, yy)) < ink_threshold:
                        pixels.append([xx - wx, yy - wy])
            if not pixels:
                continue
            matches.setdefault(label, []).append({
                "matched_pixels": pixels,
                "external_contact_pixels": [],
                "external_contacts": 0,
                "missing": 0,
                "extra": 0,
            })
            counts[label] = counts.get(label, 0) + 1
            selected_sources[word_rel] = meta

        if not matches:
            continue
        results.append({
            "source_id": f"manifest-word:{page}:{subnr}:{source_word}",
            "style": str(style),
            "expected_word": str(source_word),
            "headword": str(source_word),
            "page": page or 0,
            "subnr": str(subnr or ""),
            "word_file": word_rel,
            "width": ww,
            "height": wh,
            "baseline_y": max(0, wh - 1),
            "matches": matches,
            "rejected_candidates": {},
        })

    if not results:
        return None, raw_sources

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix="-pixel-editor-matches.json", delete=False
    )
    with tmp:
        json.dump({"results": results}, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    return Path(tmp.name), selected_sources


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
    pre.add_argument("--examples-per-char", type=int, default=3)
    args, _ = pre.parse_known_args(sys.argv[1:])

    original_argv = sys.argv[:]
    temp_matches: Path | None = None
    manifest_sources: dict[str, dict[str, object]] = {}
    converted, manifest_sources = _manifest_as_matches(
        args.matches, args.library, max(0, min(255, args.ink_threshold)), max(1, args.examples_per_char)
    )
    if converted is not None:
        temp_matches = converted
        rewritten = original_argv[:]
        # First positional argument is always argv[1] for this CLI family.
        rewritten[1] = str(converted)
        # v14 does not know this v15-only manifest sampling option.
        if "--examples-per-char" in rewritten:
            i = rewritten.index("--examples-per-char")
            del rewritten[i:i + 2]
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
            f"v15: opened bold harvest as whole-word context with {len(manifest_sources)} selected word sources; "
            f"facsimile_links={facsimile_links}"
        )
    else:
        print("v15: export persists immutable server version + latest.json and still downloads locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
