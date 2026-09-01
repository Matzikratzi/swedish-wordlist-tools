from __future__ import annotations

import argparse
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import ocr_review_five_rows_glyphs_html as ui
from . import ocr_review_row_glyphs_html as legacy
from .ocr_add_row_residual_glyphs import residual_component_pixels
from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact, render_exact_markup, render_exact_text
from .ocr_row_map_words import _owned_row_crop, _persistent_left_rule_x, _row_crop_box


def build_page_context(jsonl: Path, page_number: int, threshold: int = 210) -> dict:
    """Load immutable page geometry once for the whole editor session."""
    print(f"review: laddar sida {page_number} och segmenterar geometri en gång ...", flush=True)
    rows = list(read_jsonl(jsonl))
    source = source_for_page(rows, page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    row_map = segment_page_rows(page, threshold=threshold)
    positions = [
        (column, row_index)
        for column, column_entry in enumerate(row_map["columns"])
        for row_index, _row in enumerate(column_entry.get("rows") or [])
    ]
    print(f"review: geometri klar: {len(positions)} rader", flush=True)
    return {
        "source": source,
        "page": page,
        "row_map": row_map,
        "positions": positions,
        "threshold": threshold,
        "page_number": page_number,
    }


def load_review_state_fast(context: dict, position: tuple[int, int], models) -> dict:
    """Analyse only one row; page loading and segmentation are already done."""
    column, row_index = position
    page = context["page"]
    row_map = context["row_map"]
    threshold = context["threshold"]
    column_entry = row_map["columns"][column]
    physical_rows = column_entry.get("rows") or []
    if not 0 <= row_index < len(physical_rows):
        raise ValueError(f"row {row_index} out of range; column {column} has {len(physical_rows)} rows")
    row = physical_rows[row_index]
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(
        row,
        column=column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )
    crop, removed_neighbor_pixels = _owned_row_crop(page, row, box, threshold=threshold)
    crop, trimmed_left = legacy._trim_leading_white_columns(crop, threshold=threshold, keep=2)
    if trimmed_left:
        box = (box[0] + trimmed_left, box[1], box[2], box[3])
    result = analyse_row_exact(crop, models, threshold=threshold)
    selected = result["selected"]
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    residual = result["ink"] - covered
    residuals = residual_component_pixels(residual)

    items = []
    point_sets: dict[str, frozenset[tuple[int, int]]] = {}
    for index, match in enumerate(selected):
        item_id = f"M{index:02d}"
        points = frozenset(match.pixels)
        point_sets[item_id] = points
        items.append({
            "id": item_id,
            "kind": "match",
            "label": match.label,
            "style": match.style,
            "pixels": len(points),
            "bbox": legacy._bbox(set(points)),
        })
    for index, points in enumerate(residuals):
        item_id = f"U{index:02d}"
        point_sets[item_id] = points
        items.append({
            "id": item_id,
            "kind": "residual",
            "label": "?",
            "style": "unknown",
            "pixels": len(points),
            "bbox": legacy._bbox(set(points)),
        })

    return {
        "source": context["source"],
        "page": context["page_number"],
        "column": column,
        "row": row_index,
        "row_page_top": int(row["page_top"]),
        "row_page_bottom": int(row["page_bottom"]),
        "crop_box": box,
        "crop_width": crop.width,
        "crop_height": crop.height,
        "image": legacy._png_data_uri(crop),
        "baseline": result["baseline"],
        "covered_pixels": result["covered_pixels"],
        "source_pixels": result["source_pixels"],
        "source_ink_points": [[x, y] for x, y in sorted(result["ink"])],
        "removed_neighbor_pixels": removed_neighbor_pixels,
        "fully_exact": result["fully_exact"],
        "text": render_exact_text(selected, source_ink=result["ink"]) if selected else "",
        "markup": render_exact_markup(selected, source_ink=result["ink"]) if selected else "",
        "items": items,
        "point_sets": point_sets,
        "matches": selected,
    }


class SynchronizedStateCache:
    """Cache row states and prevent duplicate concurrent computation."""

    def __init__(self, loader):
        self.loader = loader
        self._lock = threading.RLock()
        self._states: dict[tuple[int, int], dict] = {}
        self._generation = 0

    def clear(self, reason: str) -> None:
        with self._lock:
            count = len(self._states)
            self._states.clear()
            self._generation += 1
            if count:
                print(f"review: tömmer {count} analyserade rader ({reason})", flush=True)

    def get(self, position: tuple[int, int]) -> dict:
        # Deliberately hold the lock during the row calculation. There are only
        # five visible rows, and this guarantees that browser request fan-out can
        # never calculate the same missing row several times in parallel.
        with self._lock:
            cached = self._states.get(position)
            if cached is not None:
                return cached
            column, row_index = position
            print(f"review: analyserar kolumn {column}, rad {row_index} ...", flush=True)
            state = self.loader(position)
            self._states[position] = state
            status = "exakt" if not ui.is_defective(state) else f"defekt {state['covered_pixels']}/{state['source_pixels']}"
            print(f"review: kolumn {column}, rad {row_index}: {status}", flush=True)
            return state


def main() -> int:
    ap = argparse.ArgumentParser(description="Fast synchronized five-row SAOL glyph review.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    context = build_page_context(args.jsonl, args.page, args.threshold)
    positions = context["positions"]
    initial = (args.column, args.row)
    if initial not in positions:
        raise ValueError(f"initial row {initial} is not present on page {args.page}")

    models_holder = {"models": load_facit(args.facit)}
    message = {"text": ""}
    cache = SynchronizedStateCache(lambda pos: load_review_state_fast(context, pos, models_holder["models"]))

    def refresh_models(reason: str) -> None:
        # Facit is mutable, geometry is not. Reload only the glyph bank.
        models_holder["models"] = load_facit(args.facit)
        cache.clear(reason)

    class Handler(BaseHTTPRequestHandler):
        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query)

        def _position(self, query: dict[str, list[str]]) -> tuple[int, int]:
            try:
                position = (
                    int((query.get("column") or [str(initial[0])])[0]),
                    int((query.get("row") or [str(initial[1])])[0]),
                )
            except ValueError as exc:
                raise ValueError("column and row must be integers") from exc
            if position not in positions:
                raise ValueError(f"row {position} is not present on page")
            return position

        def _anchor(self, query: dict[str, list[str]], position: tuple[int, int]) -> tuple[int, int]:
            if "anchor_column" not in query or "anchor_row" not in query:
                return position
            try:
                anchor = (int(query["anchor_column"][0]), int(query["anchor_row"][0]))
            except ValueError as exc:
                raise ValueError("anchor column and row must be integers") from exc
            return anchor if anchor in positions else position

        def _visible(self, query: dict[str, list[str]], position: tuple[int, int]):
            mode = (query.get("mode") or ["all"])[0]
            if mode not in {"all", "defects"}:
                mode = "all"
            anchor = self._anchor(query, position)
            if mode == "defects":
                direction = -1 if (query.get("scan") or ["forward"])[0] == "backward" else 1
                visible = ui.defect_packet(positions, anchor, cache.get, direction=direction)
                if visible:
                    anchor = visible[0]
            else:
                visible = ui.packet_positions(positions, position)
                anchor = visible[0]
            return visible, mode, anchor

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                query = self._query()
                if (query.get("refresh") or ["0"])[0] == "1":
                    refresh_models("manuell omräkning")
                position = self._position(query)
                visible, mode, anchor = self._visible(query, position)
                if not visible:
                    body = b"<html><body><h1>Inga defekta rader kvar.</h1><a href='/'>Visa alla rader</a></body></html>"
                else:
                    if position not in visible:
                        position = visible[0]
                    states = [cache.get(item) for item in visible]
                    body = ui.render_five_row_html(
                        states, position, positions, message["text"], mode=mode, anchor=anchor
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
            try:
                query = self._query()
                position = self._position(query)
                mode = (query.get("mode") or ["all"])[0]
                anchor = self._anchor(query, position)
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                active_state = cache.get(position)
                message["text"] = legacy.apply_edit(active_state, args.facit, form)
                refresh_models("facit ändrat")
                location = ui.row_url(position, mode=mode, anchor=anchor)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
                location = ui.row_url(initial)
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}{ui.row_url(initial)}"
    print(url)
    print(
        f"facit={args.facit} (FAST: sidbild/geometri återanvänds; varje rad analyseras högst en gång åt gången; Ctrl-C avslutar)"
    )
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
