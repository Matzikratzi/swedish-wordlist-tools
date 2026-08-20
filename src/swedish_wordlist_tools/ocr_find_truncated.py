from __future__ import annotations

import argparse
import json
from pathlib import Path


def is_likely_truncated(entry: dict[str, object]) -> bool:
    text = entry.get("text")
    if not isinstance(text, str):
        return False
    # Existing SAOL14 analysis found the exported field hard-capped around 50 chars.
    # Treat 49/50 as suspicious candidates; recovery code will verify against OCR.
    return len(text) in {49, 50}


def main() -> int:
    parser = argparse.ArgumentParser(description="List likely SAOL14 text truncations from JSONL.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--page", type=int, help="Only show entries on this facsimile page")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    shown = 0
    with args.jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            if args.page is not None and entry.get("sidnr1") != args.page:
                continue
            if not is_likely_truncated(entry):
                continue
            print(json.dumps({
                "normaliserat_ord": entry.get("normaliserat_ord"),
                "subnr": entry.get("subnr"),
                "sidnr1": entry.get("sidnr1"),
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
