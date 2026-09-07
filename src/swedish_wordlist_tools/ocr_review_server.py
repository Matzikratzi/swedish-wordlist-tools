from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class ReviewHandler(SimpleHTTPRequestHandler):
    server_version = "SAOLReview/1.0"

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        raw = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/save-atlas":
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})
            return
        try:
            n = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            n = 0
        if n <= 0 or n > 100 * 1024 * 1024:
            self._send_json(400, {"ok": False, "error": "invalid content length"})
            return
        try:
            raw = self.rfile.read(n)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - surfaced to browser
            self._send_json(400, {"ok": False, "error": f"invalid JSON: {exc}"})
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("words"), list):
            self._send_json(400, {"ok": False, "error": "atlas JSON must contain a words list"})
            return

        atlas_dir: Path = self.server.atlas_dir  # type: ignore[attr-defined]
        atlas_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
        fmt = str(payload.get("format") or "atlas")
        safe_fmt = "".join(c if c.isalnum() or c in "-_." else "-" for c in fmt).strip("-.") or "atlas"
        filename = f"{stamp}-{safe_fmt}.json"
        final = atlas_dir / filename
        tmp = atlas_dir / (filename + ".tmp")
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, final)

        latest = atlas_dir / "latest.json"
        latest_tmp = atlas_dir / "latest.json.tmp"
        shutil.copyfile(final, latest_tmp)
        os.replace(latest_tmp, latest)

        meta = {
            "version_file": filename,
            "saved_at_utc": now.isoformat(),
            "format": fmt,
            "word_count": len(payload.get("words") or []),
            "latest": "latest.json",
        }
        meta_tmp = atlas_dir / "latest.meta.json.tmp"
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(meta_tmp, atlas_dir / "latest.meta.json")
        self._send_json(200, {"ok": True, **meta})


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve a generated SAOL review directory and persist browser atlas exports as immutable server-side versions.")
    ap.add_argument("root", type=Path, help="Directory containing index.html")
    ap.add_argument("--atlas-dir", type=Path, default=Path("/tmp/saol14-glyph-atlas-versions"))
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8801)
    args = ap.parse_args()
    root = args.root.resolve()
    if not (root / "index.html").exists():
        raise SystemExit(f"missing {root / 'index.html'}")
    atlas_dir = args.atlas_dir.resolve()

    class Handler(ReviewHandler):
        def __init__(self, *hargs, **hkwargs):
            super().__init__(*hargs, directory=str(root), **hkwargs)

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.atlas_dir = atlas_dir  # type: ignore[attr-defined]
    print(f"review: http://{args.bind}:{args.port}/")
    print(f"atlas versions: {atlas_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
