from __future__ import annotations

import argparse
import json
from pathlib import Path


def is_likely_truncated(entry: dict[str, object], min_length: int = 49) -> bool:
    text = entry.get("text")
    if not isinstance(text, str):
        return False
    # The export appears to have a hard cap around 50 characters, but diagnose
    # the real data rather than assuming every page contains an exact 49/50 hit.
    return len(text) >= min_length


def _page_entries(jsonl: Path, page: int | None) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            if page is not None and entry.get("sidnr1") != page:
                continue
            entries.append(entry)
    return entries


def _print_diagnostics(entries: list[dict[str, object]], limit: int) -> None:
    with_text = [entry for entry in entries if isinstance(entry.get("text"), str)]
    ranked = sorted(with_text, key=lambda entry: len(str(entry["text"])), reverse=True)
    print(json.dumps({
        "entries": len(entries),
        "entries_with_text": len(with_text),
        "max_text_length": len(str(ranked[0]["text"])) if ranked else None,
        "longest": [
            {
                "normaliserat_ord": entry.get("normaliserat_ord"),
                "subnr": entry.get("subnr"),
                "sidnr1": entry.get("sidnr1"),
                "length": len(str(entry["text"])),
                "text": entry.get("text"),
                "stycke": entry.get("stycke"),
                "ord": entry.get("ord"),
            }
            for entry in ranked[:limit]
        ],
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="List likely SAOL14 text truncations from JSONL.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--page", type=int, help="Only show entries on this facsimile page")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-length", type=int, default=49,
                        help="Minimum text length to consider suspicious (default: 49)")
    parser.add_argument("--diagnose", action="store_true",
                        help="Show text-length statistics and longest entries instead")
    args = parser.parse_args()

    entries = _page_entries(args.jsonl, args.page)
    if args.diagnose:
        _print_diagnostics(entries, args.limit)
        return 0

    shown = 0
    for entry in entries:
        if not is_likely_truncated(entry, args.min_length):
            continue
        print(json.dumps({
            "normaliserat_ord": entry.get("normaliserat_ord"),
            "subnr": entry.get("subnr"),
            "sidnr1": entry.get("sidnr1"),
            "length": len(str(entry.get("text", ""))),
            "text": entry.get("text"),
            "stycke": entry.get("stycke"),
            "ord": entry.get("ord"),
        }, ensure_ascii=False))
        shown += 1
        if shown >= args.limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
