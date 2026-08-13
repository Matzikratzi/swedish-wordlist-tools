from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .analyze_x_routing import _is_hv
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word
from .saol_wordclasses import classes_from_record

INCLUDED = {"NOUN", "ADJ", "VERB", "PRON", "NUM", "ADV"}

def analyze(records):
    counts = Counter()
    examples = defaultdict(list)
    for record in records:
        if _is_hv(record):
            continue
        word = clean_saol_word(record.get("ord"))
        if not word or word.startswith("-") or word.endswith("-"):
            continue
        for upos in sorted(set(classes_from_record(record)) - INCLUDED):
            counts[upos] += 1
            if len(examples[upos]) < 12:
                examples[upos].append({
                    "ord": word,
                    "ordkl": str(record.get("ordkl") or ""),
                    "text": str(record.get("text") or ""),
                })
    return {"counts": dict(sorted(counts.items())), "examples": dict(sorted(examples.items()))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=Path("data/raw/saol14-faksimil.jsonl"))
    args = parser.parse_args()
    report = analyze(read_jsonl(args.source))
    out = Path("reports/saol14-remaining-wordclasses.txt")
    lines = ["SAOL14: återstående ordklasser", "", "Efter UPOS:"]
    for upos, count in report["counts"].items():
        lines.append(f"  {count:6d}  {upos}")
    for upos, rows in report["examples"].items():
        lines += ["", f"[{upos}]"]
        for row in rows:
            lines.append(f"  {row['ord']!r} ordkl={row['ordkl']!r} text={row['text']!r}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path("reports/saol14-remaining-wordclasses.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Återstående:", report["counts"])
    print("Text:", out)

if __name__ == "__main__":
    main()
