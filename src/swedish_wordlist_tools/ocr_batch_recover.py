from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .ocr_find_truncated import is_likely_truncated


def _entries(jsonl: Path, min_length: int, limit: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen_subnr: set[object] = set()
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            subnr = entry.get("subnr")
            if subnr in seen_subnr:
                continue
            if not is_likely_truncated(entry, min_length):
                continue
            seen_subnr.add(subnr)
            out.append(entry)
            if len(out) >= limit:
                break
    return out


def _classify(payload: dict[str, object]) -> str:
    best = payload.get("best")
    if not isinstance(best, dict):
        return "no-match"
    stop = best.get("stop_reason")
    tail = best.get("recovered_tail")
    if stop != "next-jsonl-headword":
        return f"review:{stop}"
    if not isinstance(tail, str):
        return "review:no-tail"
    if tail == "":
        return "matched-empty-tail"
    return "matched-tail"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OCR recovery on a sample of likely truncated SAOL14 entries.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--min-length", type=int, default=50)
    parser.add_argument("--keep-workdir", type=Path)
    args = parser.parse_args()

    entries = _entries(args.jsonl, args.min_length, args.limit)
    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for entry in entries:
        subnr = entry.get("subnr")
        workdir = None
        if args.keep_workdir is not None:
            workdir = args.keep_workdir / f"subnr-{subnr}"
        cmd = [sys.executable, "-m", "swedish_wordlist_tools.ocr_recover_entry", str(args.jsonl), "--subnr", str(subnr)]
        if workdir is not None:
            cmd += ["--keep-workdir", str(workdir)]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            row = {
                "subnr": subnr,
                "normaliserat_ord": entry.get("normaliserat_ord"),
                "sidnr1": entry.get("sidnr1"),
                "status": "error",
                "error": (proc.stderr or proc.stdout).strip()[-600:],
            }
        else:
            payload = json.loads(proc.stdout)
            best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
            status = _classify(payload)
            row = {
                "subnr": subnr,
                "normaliserat_ord": entry.get("normaliserat_ord"),
                "sidnr1": entry.get("sidnr1"),
                "jsonl_text": entry.get("text"),
                "status": status,
                "recovered_tail": best.get("recovered_tail"),
                "article_remainder": best.get("article_remainder"),
                "stop_reason": best.get("stop_reason"),
                "known_text_score": best.get("known_text_score"),
                "headword_score": best.get("headword_score"),
                "match_mode": best.get("match_mode"),
                "next_entry": (payload.get("next_entry") or {}).get("normaliserat_ord") if isinstance(payload.get("next_entry"), dict) else None,
            }
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = {"sample_size": len(rows), "counts": dict(sorted(counts.items())), "rows": rows}
    print("--- SUMMARY ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
