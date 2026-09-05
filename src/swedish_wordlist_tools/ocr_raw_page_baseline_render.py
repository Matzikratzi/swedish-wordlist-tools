from __future__ import annotations

"""Render raw-page baseline debug images from a previously written JSONL trace."""

import argparse
import json
from pathlib import Path

from PIL import ImageDraw

from .ocr_column_edge_debug import _render_grid
from .ocr_page1_layout_debug import _load_thresholded_page


GRID_LEFT_PAD = 120
GRID_TOP_PAD = 40


def _read_trace(path: Path) -> tuple[dict, list[dict], dict | None]:
    meta: dict | None = None
    rows: list[dict] = []
    columns: dict[int, dict] = {}
    summary: dict | None = None
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            kind = event.get("type")
            if kind == "meta":
                if meta is not None:
                    raise RuntimeError(f"multiple meta events in {path}")
                meta = event
            elif kind == "column":
                columns[int(event["column"])] = event
            elif kind == "row":
                rows.append(event)
            elif kind == "summary":
                summary = event
    if meta is None:
        raise RuntimeError(f"no meta event in {path}")
    if columns:
        meta = dict(meta)
        meta["column_geometry"] = columns
    rows.sort(key=lambda row: (int(row.get("column", 0)), int(row["row"])))
    return meta, rows, summary


def _column_bounds(meta: dict, entry: dict) -> tuple[int, int]:
    if "left" in meta and "right" in meta:
        return int(meta["left"]), int(meta["right"])
    column = int(entry.get("column", 0))
    geometry = meta.get("column_geometry", {}).get(column)
    if geometry is None:
        raise RuntimeError(f"trace has no geometry for column {column}")
    return int(geometry["left"]), int(geometry["right"])


def _draw_snapshot(
    thresholded_page,
    meta: dict,
    rows: list[dict],
    output: Path,
    *,
    cell: int,
    y_tick: int,
    x_tick: int,
    axis_x: int,
    axis_y: int,
) -> None:
    image = _render_grid(
        thresholded_page,
        cell=cell,
        y_tick=y_tick,
        x_tick=x_tick,
        axis_x_source=axis_x,
        numbered_y=axis_y,
        row0_tops=None,
        columns=None,
    )
    draw = ImageDraw.Draw(image)

    seen_initial: set[int] = set()
    for entry in rows:
        column = int(entry.get("column", 0))
        left, right = _column_bounds(meta, entry)
        x0 = GRID_LEFT_PAD + left * cell
        x1 = GRID_LEFT_PAD + right * cell
        label_x = x1 + 4

        if column not in seen_initial:
            initial_border = entry.get("initial_border")
            if initial_border is not None:
                y = GRID_TOP_PAD + int(initial_border) * cell
                draw.line((x0, y, x1, y), fill=(120, 120, 120), width=1)
                draw.text(
                    (label_x, y - 5),
                    f"c{column} initial_border={initial_border}",
                    fill=(90, 90, 90),
                )
            seen_initial.add(column)

        top_y = GRID_TOP_PAD + int(entry["debug_top"]) * cell
        baseline_y = GRID_TOP_PAD + int(entry["baseline"]) * cell
        border_y = GRID_TOP_PAD + int(entry["border"]) * cell
        draw.line((x0, top_y, x1, top_y), fill=(255, 0, 0), width=1)
        draw.line((x0, baseline_y, x1, baseline_y), fill=(0, 80, 255), width=1)
        draw.line((x0, border_y, x1, border_y), fill=(0, 170, 0), width=1)
        prefix = f"c{column}r{int(entry['row'])}" if meta.get("mode") == "all" else f"r{int(entry['row'])}"
        draw.text(
            (label_x, top_y - 5),
            f"{prefix} debug_top={entry['debug_top']}",
            fill=(255, 0, 0),
        )
        draw.text(
            (label_x, baseline_y - 5),
            f"base={entry['baseline']}",
            fill=(0, 80, 255),
        )
        draw.text(
            (label_x, border_y - 5),
            f"border={entry['border']}",
            fill=(0, 140, 0),
        )

        probe_x = entry.get("probe_x")
        probe_y = entry.get("probe_y")
        if probe_x is not None and probe_y is not None:
            px = GRID_LEFT_PAD + int(probe_x) * cell + cell // 2
            py0 = GRID_TOP_PAD + int(probe_y) * cell
            py1 = GRID_TOP_PAD + (int(probe_y) + 10) * cell
            draw.line((px, py0, px, py1), fill=(255, 0, 0), width=2)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _step_output(base: Path, entry: dict) -> Path:
    suffix = base.suffix or ".png"
    row = int(entry["row"])
    if "column" in entry:
        return base.with_name(f"{base.stem}-c{int(entry['column'])}-row{row:03d}{suffix}")
    return base.with_name(f"{base.stem}-row{row:03d}{suffix}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render PNG debug geometry from ocr_raw_page_baseline_debug JSONL output."
    )
    ap.add_argument("trace", type=Path)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--steps", action="store_true", help="also render one cumulative image per row")
    ap.add_argument("--cell", type=int, default=5)
    ap.add_argument("--tick", type=int, default=20)
    ap.add_argument("--x-tick", type=int, default=10)
    ap.add_argument("--axis-x", type=int, default=45)
    ap.add_argument("--axis-y", type=int, default=50)
    args = ap.parse_args()

    meta, rows, summary = _read_trace(args.trace)
    source_jsonl = Path(meta["source_jsonl"])
    page = int(meta["page"])
    threshold = int(meta["threshold"])
    thresholded_page = _load_thresholded_page(source_jsonl, page, threshold)

    output = args.output or args.trace.with_suffix(".png")
    _draw_snapshot(
        thresholded_page,
        meta,
        rows,
        output,
        cell=args.cell,
        y_tick=args.tick,
        x_tick=args.x_tick,
        axis_x=args.axis_x,
        axis_y=args.axis_y,
    )
    print(f"raw-page-render: rows={len(rows)} output={output}")

    if args.steps:
        for index, entry in enumerate(rows):
            step_path = _step_output(output, entry)
            _draw_snapshot(
                thresholded_page,
                meta,
                rows[: index + 1],
                step_path,
                cell=args.cell,
                y_tick=args.tick,
                x_tick=args.x_tick,
                axis_x=args.axis_x,
                axis_y=args.axis_y,
            )
            print(
                f"raw-page-render-step: column={entry.get('column')} "
                f"row={int(entry['row']):03d} output={step_path}"
            )

    if summary is not None:
        stopped_row = summary.get("stopped_row", summary.get("failed_row"))
        stopped_reason = summary.get("stopped_reason", summary.get("failed_reason"))
        stopped_column = summary.get("failed_column")
        if stopped_row is not None:
            print(
                f"raw-page-render-trace-stop: column={stopped_column} row={stopped_row} "
                f"reason={stopped_reason}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
