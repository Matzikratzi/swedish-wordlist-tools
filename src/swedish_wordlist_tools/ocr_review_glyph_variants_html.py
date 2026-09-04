from __future__ import annotations

"""Render all stored raster variants for selected glyph labels as a small HTML page."""

import argparse
import html
import json
import tempfile
import webbrowser
from collections import defaultdict
from pathlib import Path


def _role(model: dict) -> str:
    return str(model.get("role") or model.get("style") or "unknown")


def _points(model: dict) -> list[tuple[int, int]]:
    raw = model.get("pixels_relative_to_baseline") or model.get("pixels") or []
    return [(int(p[0]), int(p[1])) for p in raw if isinstance(p, (list, tuple)) and len(p) >= 2]


def _svg(points: list[tuple[int, int]], scale: int = 10) -> str:
    if not points:
        return '<div class="empty">inga pixlar</div>'
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    pad = 2
    width = right - left + 1 + 2 * pad
    height = bottom - top + 1 + 2 * pad
    rects = []
    for x, y in points:
        rx = (x - left + pad) * scale
        ry = (y - top + pad) * scale
        rects.append(f'<rect x="{rx}" y="{ry}" width="{scale}" height="{scale}"/>')
    baseline_y = (0 - top + pad + 1) * scale
    baseline = ""
    if 0 >= top - pad and 0 <= bottom + pad:
        baseline = f'<line x1="0" y1="{baseline_y}" x2="{width * scale}" y2="{baseline_y}" class="baseline"/>'
    return f'<svg viewBox="0 0 {width * scale} {height * scale}" width="{width * scale}" height="{height * scale}">{baseline}{"".join(rects)}</svg>'


def render(facit: Path, labels: list[str]) -> str:
    data = json.loads(facit.read_text(encoding="utf-8"))
    models = data.get("glyphs") or []
    wanted = set(labels)
    grouped: dict[str, dict[str, list[tuple[int, dict]]]] = defaultdict(lambda: defaultdict(list))
    for index, model in enumerate(models):
        label = str(model.get("label") or "")
        if label in wanted:
            grouped[label][_role(model)].append((index, model))

    sections = []
    for label in labels:
        roles = grouped.get(label, {})
        role_html = []
        for role in sorted(roles):
            cards = []
            for index, model in roles[role]:
                points = _points(model)
                reviewed = model.get("reviewed")
                cards.append(
                    '<div class="card">'
                    f'<div class="meta">#{index} &nbsp; {len(points)} px'
                    + (" &nbsp; reviewed" if reviewed is True else "")
                    + '</div>'
                    + _svg(points)
                    + '</div>'
                )
            role_html.append(f'<h3>{html.escape(role)}</h3><div class="cards">{"".join(cards)}</div>')
        if not role_html:
            role_html.append('<p>Inga modeller i facit.</p>')
        sections.append(f'<section><h2>{html.escape(label)}</h2>{"".join(role_html)}</section>')

    return f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>SAOL glyph variants</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#fafafa;color:#222}}
section{{margin-bottom:32px}} h2{{font-size:30px;margin-bottom:8px}} h3{{margin:14px 0 8px}}
.cards{{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}}
.card{{background:white;border:1px solid #bbb;border-radius:6px;padding:10px;min-width:110px}}
.meta{{font:12px ui-monospace,monospace;margin-bottom:8px;color:#555}}
svg{{display:block;background:#fff;border:1px solid #eee;image-rendering:pixelated}}
rect{{fill:#111}} .baseline{{stroke:#e33;stroke-width:1;opacity:.55}} .empty{{color:#888}}
</style></head><body>
<h1>Glyphvarianter</h1><p>Facit: <code>{html.escape(str(facit))}</code>. Röd linje = baseline.</p>
{"".join(sections)}
</body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Visa alla facitvarianter för valda glypher")
    parser.add_argument("--facit", required=True, type=Path)
    parser.add_argument("--glyph", action="append", required=True, dest="glyphs")
    parser.add_argument("--output", type=Path, help="Skriv HTML hit i stället för temporär fil")
    parser.add_argument("--no-open", action="store_true", help="Öppna inte webbläsaren")
    args = parser.parse_args()

    page = render(args.facit, args.glyphs)
    if args.output:
        target = args.output
        target.write_text(page, encoding="utf-8")
    else:
        handle = tempfile.NamedTemporaryFile(prefix="saol-glyph-variants-", suffix=".html", delete=False)
        target = Path(handle.name)
        handle.close()
        target.write_text(page, encoding="utf-8")
    print(target)
    if not args.no_open:
        webbrowser.open(target.resolve().as_uri())


if __name__ == "__main__":
    main()
