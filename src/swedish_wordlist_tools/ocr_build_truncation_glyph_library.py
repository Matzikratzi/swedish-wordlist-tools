from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


FALLBACK_CHARS = "abcdefghijklmnopqrstuvwxyzåäö0123456789+-.,;:()[]/=%_’'"


def _discover_chars(jsonl: Path) -> str:
    """Return every non-whitespace character occurring in JSONL text fields.

    The truncation target is the JSONL `text` string, so its actual character
    inventory is the right default alphabet. Letters are folded to lowercase;
    punctuation, digits and symbols are kept literally.
    """
    chars: set[str] = set()
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            for ch in text:
                if ch.isspace():
                    continue
                chars.add(ch.lower() if ch.isalpha() else ch)
    if not chars:
        return FALLBACK_CHARS
    # Stable output: letters, digits, then the rest by code point.
    return "".join(sorted(chars, key=lambda ch: (0 if ch.isalpha() else 1 if ch.isdigit() else 2, ch)))


def _page_char_supply(jsonl: Path, wanted: set[str]) -> tuple[dict[int, Counter[str]], dict[int, int]]:
    supply: dict[int, Counter[str]] = defaultdict(Counter)
    entries: dict[int, int] = defaultdict(int)
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            page = entry.get("sidnr1")
            text = entry.get("text")
            if not isinstance(page, int) or not isinstance(text, str) or not text:
                continue
            entries[page] += 1
            for ch in text:
                key = ch.lower() if ch.isalpha() else ch
                if key in wanted:
                    supply[page][key] += 1
    return dict(supply), dict(entries)


def _select_pages(
    supply: dict[int, Counter[str]],
    chars: str,
    target_per_char: int,
    max_pages: int,
) -> tuple[list[int], dict[str, int]]:
    remaining = {ch: target_per_char for ch in chars}
    selected: list[int] = []
    available = set(supply)

    while available and len(selected) < max_pages and any(v > 0 for v in remaining.values()):
        best_page = None
        best_score = 0.0
        best_gain: Counter[str] | None = None
        for page in available:
            counts = supply[page]
            gain = Counter({ch: min(remaining[ch], counts.get(ch, 0)) for ch in chars if remaining[ch] > 0})
            # Rare characters matter more than yet another common letter.
            score = sum((n / max(1, target_per_char)) * (1.0 + 2.0 * remaining[ch] / target_per_char) for ch, n in gain.items())
            if score > best_score:
                best_page = page
                best_score = score
                best_gain = gain
        if best_page is None or best_gain is None or best_score <= 0:
            break
        selected.append(best_page)
        available.remove(best_page)
        for ch, n in best_gain.items():
            remaining[ch] = max(0, remaining[ch] - n)

    estimated = {ch: target_per_char - remaining[ch] for ch in chars}
    return selected, estimated


def _page_spec(pages: list[int]) -> str:
    return ",".join(str(page) for page in pages)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select pages across SAOL14 and build a strict global italic glyph library for truncation recovery."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--chars", default=None,
                        help="Characters to mine. Default: all non-whitespace characters actually found in JSONL text fields.")
    parser.add_argument("--target-per-char", type=int, default=30,
                        help="Estimated JSONL occurrences to cover per character before strict OCR filtering")
    parser.add_argument("--limit-per-char", type=int, default=30,
                        help="Maximum accepted glyph templates emitted per character per mining call")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--keep-workdir", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    chars = "".join(dict.fromkeys((args.chars if args.chars is not None else _discover_chars(args.jsonl))))
    supply, entries = _page_char_supply(args.jsonl, set(chars))
    pages, estimated = _select_pages(supply, chars, args.target_per_char, args.max_pages)

    plan = {
        "chars": chars,
        "character_count": len(chars),
        "target_per_char": args.target_per_char,
        "max_pages": args.max_pages,
        "selected_pages": pages,
        "selected_page_count": len(pages),
        "estimated_jsonl_supply": estimated,
        "entries_on_selected_pages": sum(entries.get(page, 0) for page in pages),
    }
    print(json.dumps({"plan": plan}, ensure_ascii=False, indent=2), flush=True)
    if args.plan_only or not pages:
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m", "swedish_wordlist_tools.ocr_mine_jsonl_pages",
        str(args.jsonl),
        "--pages", _page_spec(pages),
        "--chars", chars,
        "--styles", "italic",
        "--limit-per-char", str(args.limit_per_char),
        "--out-dir", str(args.out_dir),
    ]
    if args.keep_workdir is not None:
        cmd += ["--keep-workdir", str(args.keep_workdir)]

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return proc.returncode

    manifest = args.out_dir / "truncation-glyph-plan.json"
    manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
