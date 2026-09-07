from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ALPHABET = "abcdefghijklmnopqrstuvwxyzåäö"
STYLES = ("italic", "roman", "bold")


def _is_manual(ann: dict[str, object]) -> bool:
    status = str(ann.get("candidate_status") or "manual")
    return status == "manual"


def _ann_style(word: dict[str, object], ann: dict[str, object]) -> str:
    return str(ann.get("style") or word.get("style") or "roman")


def _is_obsolete_stylecopy(word: dict[str, object]) -> bool:
    return str(word.get("source_id") or "").endswith("::stylecopy")


def _physical_key(word: dict[str, object]) -> tuple[str, str, str, str]:
    # word_file is strongest because historical style-copy rows reused the exact
    # same raster.  The other fields keep the key useful for older atlases.
    return (
        str(word.get("word_file") or ""),
        str(word.get("page") or ""),
        str(word.get("subnr") or ""),
        str(word.get("expected_word") or ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize manually learned SAOL glyphs and make a representative editor atlas.")
    ap.add_argument("atlas", type=Path)
    ap.add_argument("--examples-per-glyph", type=int, default=3)
    ap.add_argument("--review-out", type=Path, required=True)
    ap.add_argument("--table-out", type=Path, required=True)
    args = ap.parse_args()

    payload = json.loads(args.atlas.read_text(encoding="utf-8"))
    raw_words = [w for w in payload.get("words", []) if isinstance(w, dict)]

    # Old editors created hidden per-style copies of the same raster row.  Since
    # style is now per annotation, those rows are obsolete training/review data.
    # Drop explicit ::stylecopy rows and deduplicate any remaining identical
    # physical word rasters, preferring the first/original row.
    words: list[dict[str, object]] = []
    seen_physical: set[tuple[str, str, str, str]] = set()
    dropped_stylecopies = 0
    dropped_duplicates = 0
    for word in raw_words:
        if _is_obsolete_stylecopy(word):
            dropped_stylecopies += 1
            continue
        key = _physical_key(word)
        if key in seen_physical:
            dropped_duplicates += 1
            continue
        seen_physical.add(key)
        words.append(word)

    target = max(1, args.examples_per_glyph)

    overall: Counter[str] = Counter()
    by_style: dict[str, Counter[str]] = {s: Counter() for s in STYLES}
    occurrences: dict[tuple[str, str], list[int]] = defaultdict(list)

    for wi, word in enumerate(words):
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict) or not _is_manual(ann):
                continue
            label = str(ann.get("label") or "")
            if not label:
                continue
            style = _ann_style(word, ann)
            overall[label] += 1
            by_style.setdefault(style, Counter())[label] += 1
            if wi not in occurrences[(style, label)]:
                occurrences[(style, label)].append(wi)

    # Greedy set cover: choose as few full-word cards as practical while giving
    # each learned glyph/style up to N distinct word contexts.
    needs: dict[tuple[str, str], int] = {
        key: min(target, len(idxs)) for key, idxs in occurrences.items() if key[1] != "·"
    }
    chosen: list[int] = []
    chosen_set: set[int] = set()
    while any(n > 0 for n in needs.values()):
        best_i = None
        best_gain = 0
        for wi, _word in enumerate(words):
            if wi in chosen_set:
                continue
            gain = sum(1 for key, n in needs.items() if n > 0 and wi in occurrences.get(key, []))
            if gain > best_gain:
                best_i, best_gain = wi, gain
        if best_i is None or best_gain == 0:
            break
        chosen.append(best_i)
        chosen_set.add(best_i)
        for key in list(needs):
            if needs[key] > 0 and best_i in occurrences.get(key, []):
                needs[key] -= 1

    review = dict(payload)
    review["format"] = "saol-manual-pixel-atlas-corrected-glyph-review-v2"
    review["review_progress"] = None
    review["words"] = [words[i] for i in chosen]
    args.review_out.parent.mkdir(parents=True, exist_ok=True)
    args.review_out.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["glyph\ttotal\titalic\troman\tbold\tstatus"]
    for ch in ALPHABET:
        total = overall[ch]
        status = "SAKNAS" if total == 0 else ("SVAG" if total < target else "OK")
        lines.append(
            f"{ch}\t{total}\t{by_style.get('italic', Counter())[ch]}\t{by_style.get('roman', Counter())[ch]}\t{by_style.get('bold', Counter())[ch]}\t{status}"
        )
    for ch in sorted(k for k in overall if k not in ALPHABET):
        lines.append(
            f"{ch}\t{overall[ch]}\t{by_style.get('italic', Counter())[ch]}\t{by_style.get('roman', Counter())[ch]}\t{by_style.get('bold', Counter())[ch]}\tSYMBOL"
        )
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    args.table_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    present = "".join(ch for ch in ALPHABET if overall[ch])
    missing = " ".join(ch for ch in ALPHABET if not overall[ch]) or "INGA"
    weak = " ".join(f"{ch}:{overall[ch]}" for ch in ALPHABET if 0 < overall[ch] < target) or "INGA"
    print(f"words_in_atlas={len(raw_words)} usable_words={len(words)} review_words={len(chosen)} examples_per_glyph={target}")
    print(f"dropped_stylecopies={dropped_stylecopies} dropped_duplicate_rasters={dropped_duplicates}")
    print(f"present={present}")
    print(f"missing={missing}")
    print(f"under_{target}={weak}")
    print(f"table={args.table_out}")
    print(f"review_atlas={args.review_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
