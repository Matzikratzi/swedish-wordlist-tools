from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlencode, urlparse

from .ocr_compare_page_text_prefix import _format_duration
from .ocr_glyph_matcher import Match, load_facit
from .ocr_page_glyph_audit import is_cluster_label
from .ocr_review_five_rows_glyphs_boundary_html import load_review_state_with_cached_boundaries
from .ocr_review_five_rows_glyphs_fast_html import build_page_context

DEFAULT_REVIEW = Path("glyphs/saol14-cluster-review.json")
REVIEW_FORMAT = "saol14-cluster-review-v1"


def model_relative_pixels(match: Match) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(x) - int(match.x), int(y) - int(match.baseline)) for x, y in match.pixels))


def cluster_model_fingerprint(match: Match) -> str:
    payload = {
        "label": str(match.label),
        "style": str(match.style),
        "pixels_relative_to_baseline": model_relative_pixels(match),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _model_pixels_data(match: Match) -> list[list[int]]:
    return [[x, y] for x, y in model_relative_pixels(match)]


def collect_cluster_models(context: dict, models, *, progress=None) -> list[dict]:
    grouped: dict[str, dict] = {}
    positions = list(context.get("positions") or [])
    for done, position in enumerate(positions, start=1):
        state = load_review_state_with_cached_boundaries(context, position, models)
        for match in state.get("matches") or []:
            if not is_cluster_label(match.label):
                continue
            fingerprint = cluster_model_fingerprint(match)
            entry = grouped.get(fingerprint)
            if entry is None:
                relative = model_relative_pixels(match)
                xs = [x for x, _y in relative]
                ys = [y for _x, y in relative]
                entry = {
                    "fingerprint": fingerprint,
                    "label": str(match.label),
                    "style": str(match.style),
                    "sources": int(getattr(match, "sources", 0) or 0),
                    "model_pixels": [[x, y] for x, y in relative],
                    "model_bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "uses": [],
                }
                grouped[fingerprint] = entry
            xs = [x for x, _y in match.pixels]
            ys = [y for _x, y in match.pixels]
            entry["uses"].append(
                {
                    "page": int(state["page"]),
                    "column": int(state["column"]),
                    "row": int(state["row"]),
                    "text": str(state.get("text") or ""),
                    "image": str(state.get("image") or ""),
                    "crop_width": int(state.get("crop_width") or 0),
                    "crop_height": int(state.get("crop_height") or 0),
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "x": int(match.x),
                    "baseline": int(match.baseline),
                    "pixels": [[int(x), int(y)] for x, y in sorted(match.pixels)],
                }
            )
        if progress is not None:
            progress(done, len(positions), position)

    result = list(grouped.values())
    for entry in result:
        entry["uses"].sort(key=lambda use: (use["page"], use["column"], use["row"], use["bbox"][0]))
    return sorted(result, key=lambda item: (item["label"].casefold(), item["style"], item["fingerprint"]))


def load_reviews(path: Path) -> dict:
    if not path.exists():
        return {"format": REVIEW_FORMAT, "models": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != REVIEW_FORMAT:
        raise ValueError(f"unsupported cluster review format: {payload.get('format')!r}")
    models = payload.get("models")
    if not isinstance(models, dict):
        raise ValueError("cluster review models must be an object")
    return payload


def save_review(path: Path, model: dict, status: str) -> None:
    if status not in {"approved", "rejected"}:
        raise ValueError(f"bad cluster review status: {status!r}")
    payload = load_reviews(path)
    payload.setdefault("models", {})[model["fingerprint"]] = {
        "status": status,
        "label": model["label"],
        "style": model["style"],
        "pixels_relative_to_baseline": model["model_pixels"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def review_statuses(path: Path) -> dict[str, str]:
    payload = load_reviews(path)
    return {
        str(fingerprint): str(record.get("status") or "pending")
        for fingerprint, record in (payload.get("models") or {}).items()
    }


def _url(model_index: int, use_index: int = 0, *, pending_only: bool = True) -> str:
    return "/?" + urlencode(
        {
            "model": int(model_index),
            "use": int(use_index),
            "pending": "1" if pending_only else "0",
        }
    )


def _nav_index(index: int, count: int, delta: int) -> int:
    if count <= 0:
        return 0
    return (index + delta) % count


def render_page(models: list[dict], statuses: dict[str, str], model_index: int, use_index: int, *, pending_only: bool, message: str = "") -> str:
    visible = [m for m in models if not pending_only or statuses.get(m["fingerprint"], "pending") != "approved"]
    if not visible:
        return """<!doctype html><meta charset='utf-8'><title>Cluster review</title><h1>Alla klustermodeller är godkända.</h1><p><a href='/?pending=0'>Visa även godkända</a></p>"""

    model_index %= len(visible)
    model = visible[model_index]
    uses = model["uses"]
    use_index %= len(uses)
    use = uses[use_index]
    status = statuses.get(model["fingerprint"], "pending")
    bbox = use["bbox"]
    model_bbox = model["model_bbox"]
    model_w = model_bbox[2] - model_bbox[0] + 1
    model_h = model_bbox[3] - model_bbox[1] + 1

    prev_model = _url(_nav_index(model_index, len(visible), -1), 0, pending_only=pending_only)
    next_model = _url(_nav_index(model_index, len(visible), 1), 0, pending_only=pending_only)
    prev_use = _url(model_index, _nav_index(use_index, len(uses), -1), pending_only=pending_only)
    next_use = _url(model_index, _nav_index(use_index, len(uses), 1), pending_only=pending_only)
    toggle = _url(model_index, use_index, pending_only=not pending_only)
    label = html.escape(model["label"])
    style = html.escape(model["style"])
    text = html.escape(use["text"])
    message_html = f"<p class='message'>{html.escape(message)}</p>" if message else ""

    state_json = json.dumps(
        {
            "image": use["image"],
            "width": use["crop_width"],
            "height": use["crop_height"],
            "bbox": bbox,
            "pixels": use["pixels"],
            "model_pixels": model["model_pixels"],
            "model_bbox": model_bbox,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>SAOL cluster review</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1500px;margin:22px auto;padding:0 18px}}
nav{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}}
a,button{{padding:7px 11px;border:1px solid #888;border-radius:5px;background:#f7f7f7;color:#111;text-decoration:none;font:inherit}}
button.approve{{background:#e8f6e8}} button.reject{{background:#fdeaea}}
.meta{{font-family:monospace;white-space:pre-wrap}} .message{{font-weight:700}}
.rowbox{{overflow:auto;border:1px solid #bbb;padding:10px;background:white}} canvas{{image-rendering:pixelated}}
.status-approved{{color:#167016}} .status-rejected{{color:#a31616}} .status-pending{{color:#775c00}}
.small{{font-size:.9em;color:#555}}
</style></head><body>
<h1>SAOL klustergranskning – sida {use['page']}</h1>
{message_html}
<nav>
<a href='{prev_model}'>&larr; föregående modell</a>
<b>modell {model_index + 1}/{len(visible)}</b>
<a href='{next_model}'>nästa modell &rarr;</a>
<a href='{toggle}'>{'Visa alla' if pending_only else 'Dölj godkända'}</a>
</nav>
<h2><code>{label}</code> <small>{style}</small></h2>
<div class='meta'>fingerprint={model['fingerprint']}
sources={model['sources']}   användningar på sidan={len(uses)}   raster={model_w}x{model_h}
status=<span class='status-{status}'>{status}</span></div>
<form method='post' action='{_url(model_index, use_index, pending_only=pending_only)}' style='margin:12px 0'>
<input type='hidden' name='fingerprint' value='{model['fingerprint']}'>
<button class='approve' name='status' value='approved'>Godkänn modellen</button>
<button class='reject' name='status' value='rejected'>Fel modell</button>
</form>
<h3>Modellraster</h3>
<div class='rowbox'><canvas id='modelCanvas'></canvas></div>
<h3>Träff {use_index + 1}/{len(uses)}</h3>
<nav><a href='{prev_use}'>&larr; föregående träff</a><a href='{next_use}'>nästa träff &rarr;</a></nav>
<div class='meta'>col={use['column']} row={use['row']} x={bbox[0]}..{bbox[2]} y={bbox[1]}..{bbox[3]}</div>
<p><code>{text}</code></p>
<div class='rowbox'><canvas id='rowCanvas'></canvas></div>
<p class='small'>Rött = klustrets box. Blå halvtransparenta rutor = pixlar som just denna klustermatch äger.</p>
<script>
const S={state_json};
const scale=7;
const row=document.getElementById('rowCanvas'), rc=row.getContext('2d');
const img=new Image(); img.src=S.image;
img.onload=()=>{{
 row.width=S.width*scale; row.height=S.height*scale; rc.imageSmoothingEnabled=false;
 rc.drawImage(img,0,0,row.width,row.height);
 rc.fillStyle='rgba(20,90,220,.28)';
 for(const [x,y] of S.pixels) rc.fillRect(x*scale,y*scale,scale,scale);
 const [x0,y0,x1,y1]=S.bbox; rc.strokeStyle='rgba(210,20,20,.95)'; rc.lineWidth=2;
 rc.strokeRect(x0*scale+.5,y0*scale+.5,(x1-x0+1)*scale,(y1-y0+1)*scale);
}};
const mc=document.getElementById('modelCanvas'), mctx=mc.getContext('2d');
const [mx0,my0,mx1,my1]=S.model_bbox, ms=12, mpad=2;
mc.width=(mx1-mx0+1+2*mpad)*ms; mc.height=(my1-my0+1+2*mpad)*ms;
mctx.fillStyle='white';mctx.fillRect(0,0,mc.width,mc.height);mctx.fillStyle='black';
for(const [x,y] of S.model_pixels) mctx.fillRect((x-mx0+mpad)*ms,(y-my0+mpad)*ms,ms,ms);
mctx.strokeStyle='rgba(100,100,100,.25)';mctx.lineWidth=1;
for(let x=0;x<=mc.width;x+=ms){{mctx.beginPath();mctx.moveTo(x+.5,0);mctx.lineTo(x+.5,mc.height);mctx.stroke();}}
for(let y=0;y<=mc.height;y+=ms){{mctx.beginPath();mctx.moveTo(0,y+.5);mctx.lineTo(mc.width,y+.5);mctx.stroke();}}
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Visual, model-centred review of multi-character SAOL glyph clusters.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    context = build_page_context(args.jsonl, args.page, args.threshold)
    models = load_facit(args.facit)
    started = perf_counter()
    last_bucket = -1

    def progress(done: int, total: int, position: tuple[int, int]) -> None:
        nonlocal last_bucket
        percent = int(100 * done / total) if total else 100
        bucket = percent // 5
        if bucket == last_bucket and done not in {1, total}:
            return
        last_bucket = bucket
        elapsed = perf_counter() - started
        eta = elapsed * (total - done) / done if done else 0.0
        rate = done / elapsed if elapsed else 0.0
        print(
            f"cluster-review page={args.page}: {done}/{total} ({percent:3d}%) "
            f"col={position[0]} row={position[1]} elapsed={_format_duration(elapsed)} "
            f"eta={_format_duration(eta)} rate={rate:.2f} rad/s",
            file=sys.stderr,
            flush=True,
        )

    print(f"cluster-review page={args.page}: analyserar sidan boundary-aware ...", flush=True)
    cluster_models = collect_cluster_models(context, models, progress=progress)
    print(
        f"cluster-review page={args.page}: {len(cluster_models)} unika rastermodeller, "
        f"{sum(len(model['uses']) for model in cluster_models)} träffar; review={args.review}",
        flush=True,
    )
    message = {"text": ""}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            query = parse_qs(urlparse(self.path).query)
            try:
                model_index = int((query.get("model") or ["0"])[0])
                use_index = int((query.get("use") or ["0"])[0])
                pending_only = (query.get("pending") or ["1"])[0] != "0"
                body = render_page(
                    cluster_models,
                    review_statuses(args.review),
                    model_index,
                    use_index,
                    pending_only=pending_only,
                    message=message["text"],
                ).encode("utf-8")
                message["text"] = ""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            query = parse_qs(urlparse(self.path).query)
            pending_only = (query.get("pending") or ["1"])[0] != "0"
            try:
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                fingerprint = (form.get("fingerprint") or [""])[0]
                status = (form.get("status") or [""])[0]
                by_fingerprint = {model["fingerprint"]: model for model in cluster_models}
                if fingerprint not in by_fingerprint:
                    raise ValueError("unknown cluster fingerprint")
                save_review(args.review, by_fingerprint[fingerprint], status)
                model = by_fingerprint[fingerprint]
                message["text"] = f"{model['label']!r} {model['style']}: {status}"
                print(
                    f"cluster-review: {status} label={model['label']!r} style={model['style']} "
                    f"fingerprint={fingerprint}",
                    flush=True,
                )
                # After approval, pending-only mode naturally advances because
                # the approved model disappears from the visible list.
                location = _url(0 if status == "approved" and pending_only else int((query.get("model") or ["0"])[0]), 0, pending_only=pending_only)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
                location = "/"
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("cluster-review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
