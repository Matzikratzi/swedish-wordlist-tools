from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .ocr_saol_normalize import normalize_text_for_match


_BOLD_RE = re.compile(r"<b>(.*?)</b>", flags=re.IGNORECASE | re.DOTALL)


def _headword(entry: dict[str, object]) -> str | None:
    text = entry.get("text")
    if not isinstance(text, str):
        return None
    match = _BOLD_RE.search(text)
    if not match:
        return None
    word = normalize_text_for_match(match.group(1)).replace("|", "").strip()
    return word or None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pick SAOL pages containing a bold headword for each requested initial."
    )
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--chars", default="abcdefghijklmnopqrstuvwxyzåäö")
    parser.add_argument("--per-char", type=int, default=3)
    args = parser.parse_args()

    wanted = list(dict.fromkeys(args.chars))
    found: dict[str, list[dict[str, object]]] = {ch: [] for ch in wanted}

    with args.jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            page = entry.get("sidnr1")
            if not isinstance(page, int):
                continue
            word = _headword(entry)
            if not word:
                continue
            initial = word[0].casefold()
            if initial not in found or len(found[initial]) >= args.per_char:
                continue
            found[initial].append(
                {"page": page, "headword": word, "subnr": entry.get("subnr")}
            )
            if all(len(items) >= args.per_char for items in found.values()):
                break

    pages = sorted({int(item["page"]) for items in found.values() for item in items})
    missing = [ch for ch in wanted if not found[ch]]
    result = {
        "chars": wanted,
        "per_char": args.per_char,
        "pages": pages,
        "pages_arg": ",".join(str(page) for page in pages),
        "missing": missing,
        "examples": found,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
