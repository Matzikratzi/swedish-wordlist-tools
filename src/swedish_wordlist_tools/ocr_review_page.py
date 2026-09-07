from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _template_card(item: dict[str, object], templates: Path) -> str:
    fname = str(item.get("template") or "")
    img = ""
    if fname:
        path = templates / fname
        if path.exists():
            img = f'<img class="glyph" src="{_data_uri(path)}" alt="template">'
    return (
        '<div class="template-card">'
        f'{img}'
        f'<div><b>{html.escape(str(item.get("candidate", "?")))}</b></div>'
        f'<div>score {html.escape(str(item.get("score", "")))}</div>'
        f'<div class="filename">{html.escape(fname)}</div>'
        '</div>'
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a static HTML review page for ambiguous SAOL OCR glyphs.")
    p.add_argument("comparison_json", type=Path, help="JSON output from ocr_glyph_compare")
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--show-per-class", type=int, default=7)
    args = p.parse_args()

    data = json.loads(args.comparison_json.read_text(encoding="utf-8"))
    observed = data.get("observed_crop")
    context = data.get("context_crop")
    nearest = data.get("nearest_templates", [])
    summaries = data.get("candidate_summaries", [])

    observed_html = "<p>Ingen observerad crop sparades.</p>"
    if observed:
        path = Path(str(observed))
        if path.exists():
            observed_html = f'<img class="observed" src="{_data_uri(path)}" alt="observed glyph">'

    context_html = "<p>Ingen kontextbild sparades.</p>"
    if context:
        path = Path(str(context))
        if path.exists():
            context_html = f'<img class="context" src="{_data_uri(path)}" alt="word context">'

    summary_rows = []
    candidates: list[str] = []
    for item in summaries if isinstance(summaries, list) else []:
        candidate = str(item.get("candidate", "?"))
        candidates.append(candidate)
        summary_rows.append(
            "<tr>"
            f"<td><b>{html.escape(candidate)}</b></td>"
            f"<td>{html.escape(str(item.get('template_count', '')))}</td>"
            f"<td>{html.escape(str(item.get('used_count', '')))}</td>"
            f"<td>{html.escape(str(item.get('best_score', '')))}</td>"
            f"<td><b>{html.escape(str(item.get('median_top_score', '')))}</b></td>"
            f"<td>{html.escape(str(item.get('mean_top_score', '')))}</td>"
            "</tr>"
        )

    groups = []
    if isinstance(nearest, list):
        for candidate in candidates:
            items = [x for x in nearest if str(x.get("candidate")) == candidate][: args.show_per_class]
            cards = "".join(_template_card(x, args.templates) for x in items)
            groups.append(
                f'<section><h3>Kandidat {html.escape(candidate)} — {len(items)} närmaste mallar</h3>'
                f'<div class="templates">{cards}</div></section>'
            )

    best = data.get("best_candidate") or {}
    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL OCR review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1200px;color:#222}}
.meta{{background:#f5f5f5;padding:1rem 1.25rem;border-radius:8px;margin-bottom:1.5rem}}
.context{{image-rendering:pixelated;display:block;max-width:100%;margin-bottom:1rem;border:1px solid #bbb}}
.observed{{image-rendering:pixelated;transform:scale(2);transform-origin:left top;margin:0 1rem 1.5rem 0;border:1px solid #bbb;background:white}}
table{{border-collapse:collapse;margin:1rem 0 2rem 0}}
th,td{{border:1px solid #ccc;padding:.45rem .65rem;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
.templates{{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:2rem}}
.template-card{{border:1px solid #ccc;border-radius:7px;padding:.6rem;min-width:120px}}
.glyph{{image-rendering:pixelated;transform:scale(2);transform-origin:left top;margin:0 1rem 1.25rem 0;background:white}}
.filename{{font-size:10px;max-width:180px;overflow-wrap:anywhere;margin-top:.3rem;color:#555}}
code{{font-size:13px}}
</style>
<h1>SAOL OCR glyph review</h1>
<div class="meta">
<p><b>OCR-ord:</b> {html.escape(str(data.get('word', '')))} &nbsp; <b>stil:</b> {html.escape(str(data.get('style', '')))}</p>
<p><b>Position:</b> {html.escape(str(data.get('index', '')))} &nbsp; <b>OCR-tecken:</b> {html.escape(str(data.get('ocr_character', '')))}</p>
<p><b>Ord-bbox:</b> <code>{html.escape(str(data.get('word_bbox', '')))}</code> &nbsp; <b>tecken-bbox:</b> <code>{html.escape(str(data.get('glyph_bbox_in_image', '')))}</code></p>
<p><b>Ensemblevinnare:</b> {html.escape(str(best.get('candidate', '')))} &nbsp; <b>klassmarginal:</b> {html.escape(str(data.get('class_margin', '')))}</p>
</div>
<h2>Kontext</h2>
{context_html}
<h2>Observerat tecken</h2>
{observed_html}
<h2>Ensemble</h2>
<table><thead><tr><th>Kandidat</th><th>Mallar</th><th>Använda</th><th>Bäst</th><th>Median topp</th><th>Medel topp</th></tr></thead>
<tbody>{''.join(summary_rows)}</tbody></table>
<h2>Närmaste verkliga SAOL-mallar</h2>
{''.join(groups)}
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
