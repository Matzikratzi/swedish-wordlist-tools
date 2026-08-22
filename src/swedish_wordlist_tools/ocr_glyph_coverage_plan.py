from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .ocr_saol_normalize import normalize_text_for_match
from .ocr_typography_segments import classify_inflection_text, printed_text


DEFAULT_CHARS = "abcdefghijklmnopqrstuvwxyzåäö|~-,.;:+()/:"


def _canon(text: str) -> str:
    # Keep the semantic characters distinct. printed_text handles SAOL display
    # conventions; do not alias punctuation classes here.
    return printed_text(normalize_text_for_match(text))


def _page_of(row: dict[str, object]) -> int | None:
    for key in ("sida", "page", "sidnr"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _iter_style_chars(text: str):
    canon = _canon(text)
    # classify_inflection_text operates on the source text offsets; in normal
    # SAOL text printed_text is length preserving for ordinary characters. For
    # planning we only need candidate pages, not exact glyph positions.
    segs = classify_inflection_text(text)
    for seg in segs:
        style = seg.style
        if style not in {"roman", "italic"}:
            continue
        frag = _canon(text[seg.start:seg.end])
        # Square-bracket material is not useful training text for this project.
        frag = re.sub(r"\[[^\]]*\]", "", frag)
        for ch in frag:
            if not ch.isspace():
                yield style, ch


def _load_existing(manifests: list[Path]) -> dict[str, Counter[str]]:
    out = {"roman": Counter(), "italic": Counter()}
    for path in manifests:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        style = str(payload.get("style") or "roman")
        if style not in out:
            continue
        for model in payload.get("models", []):
            if not isinstance(model, dict):
                continue
            ch = model.get("character")
            n = model.get("independent_source_count", model.get("reference_count", 0))
            if isinstance(ch, str) and isinstance(n, int):
                out[style][ch] = max(out[style][ch], n)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Plan targeted SAOL pages for missing glyph/style coverage.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--consensus", type=Path, action="append", default=[],
                    help="Existing consensus manifest; repeat for roman/italic libraries")
    ap.add_argument("--target", type=int, default=20, help="Desired independent sources per style/character")
    ap.add_argument("--chars", default=DEFAULT_CHARS)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--top-candidates", type=int, default=40)
    args = ap.parse_args()

    chars = list(dict.fromkeys(args.chars))
    existing = _load_existing(args.consensus)
    needs = {
        style: {ch: max(0, args.target - existing[style].get(ch, 0)) for ch in chars}
        for style in ("roman", "italic")
    }

    page_supply: dict[int, dict[str, Counter[str]]] = defaultdict(
        lambda: {"roman": Counter(), "italic": Counter()}
    )
    page_examples: dict[int, dict[tuple[str, str], list[str]]] = defaultdict(lambda: defaultdict(list))

    with args.jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            page = _page_of(row)
            text = row.get("text")
            if page is None or not isinstance(text, str) or not text:
                continue
            local: dict[str, Counter[str]] = {"roman": Counter(), "italic": Counter()}
            for style, ch in _iter_style_chars(text):
                if ch in needs[style] and needs[style][ch] > 0:
                    local[style][ch] += 1
            if not any(local[s] for s in local):
                continue
            for style in ("roman", "italic"):
                for ch, n in local[style].items():
                    page_supply[page][style][ch] += n
                    key = (style, ch)
                    if len(page_examples[page][key]) < 3:
                        sample = text.replace("\n", " ")[:140]
                        page_examples[page][key].append(sample)

    remaining = {s: dict(v) for s, v in needs.items()}
    selected: list[dict[str, object]] = []
    unused = set(page_supply)
    for _ in range(args.max_pages):
        best_page = None
        best_gain = 0
        best_detail = None
        for page in unused:
            detail: dict[str, dict[str, int]] = {"roman": {}, "italic": {}}
            gain = 0
            for style in ("roman", "italic"):
                for ch, available in page_supply[page][style].items():
                    take = min(remaining[style].get(ch, 0), available)
                    if take > 0:
                        detail[style][ch] = take
                        gain += take
            if gain > best_gain:
                best_page, best_gain, best_detail = page, gain, detail
        if best_page is None or best_gain <= 0:
            break
        unused.remove(best_page)
        for style in ("roman", "italic"):
            for ch, take in best_detail[style].items():
                remaining[style][ch] = max(0, remaining[style][ch] - take)
        selected.append({"page": best_page, "gain": best_gain, "covers": best_detail})
        if all(v == 0 for style in remaining.values() for v in style.values()):
            break

    candidates = []
    for page, supply in page_supply.items():
        score = 0
        covers: dict[str, dict[str, int]] = {"roman": {}, "italic": {}}
        for style in ("roman", "italic"):
            for ch, n in supply[style].items():
                need = needs[style].get(ch, 0)
                if need:
                    take = min(need, n)
                    covers[style][ch] = take
                    score += take
        if score:
            candidates.append({"page": page, "score": score, "covers": covers})
    candidates.sort(key=lambda x: (-int(x["score"]), int(x["page"])))

    payload = {
        "target": args.target,
        "chars": "".join(chars),
        "existing": {s: dict(sorted(existing[s].items())) for s in existing},
        "needs_before": {s: dict(sorted(needs[s].items())) for s in needs},
        "selected_pages": selected,
        "selected_page_numbers": [x["page"] for x in selected],
        "remaining_after_plan": {s: dict(sorted(remaining[s].items())) for s in remaining},
        "top_candidate_pages": candidates[: args.top_candidates],
        "notes": {
            "purpose": "page selection only; candidates must still pass OCR/token alignment and holdout verification",
            "styles": "roman and italic planned separately",
            "strategy": "greedy set cover weighted by remaining per-character source need",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
