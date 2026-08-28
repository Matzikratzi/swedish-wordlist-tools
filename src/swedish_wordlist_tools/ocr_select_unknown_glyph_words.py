from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .ocr_glyph_matcher import load_facit

PAGE_RE = re.compile(r"SAOL14_(\d{5})\.png")


def _atomic_known(facit_path: Path) -> set[str]:
    return {m.label for m in load_facit(facit_path) if len(m.label) == 1}


def _word(row: dict[str, Any]) -> str:
    for key in ("stycke", "lemma", "headword", "word", "writtenForm", "written_form"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _page(row: dict[str, Any]) -> int | None:
    for key in ("page", "page_number", "sidnr"):
        value = row.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    source = str(row.get("source") or "")
    m = PAGE_RE.search(source)
    return int(m.group(1)) if m else None


def _subnr(row: dict[str, Any]) -> str:
    for key in ("subnr", "record_id", "id"):
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _single_unknown(word: str, known: set[str]) -> tuple[int, str] | None:
    missing = [(i, ch) for i, ch in enumerate(word) if ch not in known]
    return missing[0] if len(missing) == 1 else None


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if isinstance(value, dict):
                yield value


def select(rows: Iterable[dict[str, Any]], known: set[str], *, per_label: int = 6, max_labels: int = 30) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_sources: set[tuple[str, int | None, str]] = set()
    scanned = 0
    single_unknown = 0
    for row in rows:
        scanned += 1
        word = _word(row)
        if not word or len(word) > 40:
            continue
        missing = _single_unknown(word, known)
        if missing is None:
            continue
        single_unknown += 1
        idx, label = missing
        page = _page(row)
        subnr = _subnr(row)
        key = (word, page, subnr)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        groups[label].append({
            "expected_word": word,
            "unknown_label": label,
            "unknown_index": idx,
            "page": page,
            "subnr": subnr,
            "record_id": str(row.get("record_id") or ""),
            "source": row.get("source"),
            "lemma": row.get("lemma"),
            "stycke": row.get("stycke"),
        })

    eligible = []
    for label, candidates in groups.items():
        # Need at least two distinct source records so discovery and verification
        # can never be the same occurrence.
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda r: (r["page"] is None, r["page"] or 0, r["subnr"], r["expected_word"]))
        chosen = candidates[:per_label]
        for i, row in enumerate(chosen):
            row["harvest_half"] = "discover" if i % 2 == 0 else "verify"
        eligible.append((label, chosen, len(candidates)))

    eligible.sort(key=lambda x: (-x[2], x[0]))
    eligible = eligible[:max_labels]
    selected = [row for _, rows_, _ in eligible for row in rows_]
    return {
        "format": "saol14-unknown-glyph-word-selection-v1",
        "scanned_rows": scanned,
        "single_unknown_rows": single_unknown,
        "known_atomic_labels": sorted(known),
        "eligible_labels": len(eligible),
        "selected_words": len(selected),
        "groups": [
            {"label": label, "available": available, "selected": rows_}
            for label, rows_, available in eligible
        ],
        "words": selected,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Select SAOL JSONL entries that contain exactly one glyph label absent from facit.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-label", type=int, default=6)
    ap.add_argument("--max-labels", type=int, default=30)
    args = ap.parse_args()
    known = _atomic_known(args.facit)
    report = select(read_jsonl(args.jsonl), known, per_label=args.per_label, max_labels=args.max_labels)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scanned_rows={report['scanned_rows']}")
    print(f"single_unknown_rows={report['single_unknown_rows']}")
    print(f"eligible_labels={report['eligible_labels']}")
    print(f"selected_words={report['selected_words']}")
    for group in report["groups"]:
        words = ", ".join(row["expected_word"] for row in group["selected"])
        print(f"{group['label']!r}: available={group['available']} selected=[{words}]")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
