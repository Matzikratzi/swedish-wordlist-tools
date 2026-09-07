from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _count_chars(text: str, wanted: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for ch in text.casefold():
        if ch in wanted:
            counts[ch] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank SAOL14 pages by how many requested characters occur in JSONL text fields."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--chars", default="ce")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-text-length", type=int, default=1)
    args = parser.parse_args()

    wanted = set(args.chars.casefold())
    per_page: dict[int, Counter[str]] = defaultdict(Counter)
    entries_per_page: Counter[int] = Counter()

    with args.jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            page = entry.get("sidnr1")
            text = entry.get("text")
            if not isinstance(page, int) or not isinstance(text, str) or len(text) < args.min_text_length:
                continue
            counts = _count_chars(text, wanted)
            if not counts:
                continue
            per_page[page].update(counts)
            entries_per_page[page] += 1

    ranked = []
    for page, counts in per_page.items():
        # Prefer pages that contain the rarest requested character too, not just
        # huge totals dominated by a common character such as e.
        minimum = min((counts.get(ch, 0) for ch in wanted), default=0)
        total = sum(counts.values())
        ranked.append(
            {
                "page": page,
                "counts": {ch: counts.get(ch, 0) for ch in sorted(wanted)},
                "entries": entries_per_page[page],
                "min_requested_count": minimum,
                "total_requested_count": total,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["min_requested_count"],
            item["total_requested_count"],
            -item["page"],
        ),
        reverse=True,
    )

    output = {
        "chars": "".join(sorted(wanted)),
        "top": ranked[: args.top],
    }
    json.dump(output, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
