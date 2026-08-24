from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v17 as v17


def _inspect_input(path: Path) -> tuple[str, int, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"v18: input file does not exist: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"v18: input is not valid JSON: {path}: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit(f"v18: input JSON root must be an object: {path}")
    fmt = str(payload.get("format") or "")
    words = payload.get("words")
    results = payload.get("results")
    word_count = len(words) if isinstance(words, list) else 0
    result_count = len(results) if isinstance(results, list) else 0
    print(
        f"v18: input={path} format={fmt!r} words={word_count} results={result_count}"
    )
    is_atlas = fmt.startswith("saol-manual-pixel-atlas-corrected-") and isinstance(words, list)
    is_matches = isinstance(results, list)
    if not is_atlas and not is_matches:
        raise SystemExit(
            "v18: input is neither a corrected pixel atlas nor editor matches JSON. "
            "Expected format='saol-manual-pixel-atlas-corrected-v…' with a words list, "
            "or a top-level results list."
        )
    if is_atlas and word_count == 0:
        raise SystemExit("v18: corrected atlas contains 0 words")
    if is_matches and result_count == 0:
        raise SystemExit("v18: matches JSON contains 0 results")
    return fmt, word_count, result_count


def _restore_missing_word_crops(atlas: Path, library: Path) -> tuple[int, int, list[str], list[str]]:
    """Restore atlas word crops when a /tmp harvest directory has changed name.

    Saved atlases deliberately store word_file as a relative path. During OCR
    experiments we often regenerate the harvest into a sibling directory such
    as saol14-bold-headwords-v2. Search sibling trees for the exact relative
    path/basename and copy it into the library passed to the editor.
    """
    try:
        payload = json.loads(atlas.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, 0, [], []
    if not str(payload.get("format") or "").startswith("saol-manual-pixel-atlas-corrected-"):
        return 0, 0, [], []

    wanted: list[str] = []
    for word in payload.get("words", []):
        if isinstance(word, dict) and isinstance(word.get("word_file"), str) and word["word_file"]:
            wanted.append(word["word_file"])

    restored = 0
    missing: list[str] = []
    searched_roots: list[str] = []
    root = library.parent
    searched_roots.append(str(library))
    if root.exists():
        searched_roots.append(str(root))

    for rel in dict.fromkeys(wanted):
        dest = library / rel
        if dest.exists():
            continue
        candidates: list[Path] = []
        for sibling in root.iterdir() if root.exists() else []:
            if not sibling.is_dir() or sibling == library:
                continue
            p = sibling / rel
            if p.exists():
                candidates.append(p)
        direct = root / Path(rel).name
        if direct.exists():
            candidates.append(direct)
        if not candidates:
            missing.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidates[0], dest)
        restored += 1
    return len(dict.fromkeys(wanted)), restored, missing, searched_roots


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("matches", type=Path)
    pre.add_argument("library", type=Path)
    pre.add_argument("--out", type=Path, required=True)
    pre.add_argument("--scale")
    pre.add_argument("--margin")
    pre.add_argument("--ink-threshold")
    pre.add_argument("--examples-per-char")
    args, _ = pre.parse_known_args(sys.argv[1:])

    fmt, word_count, result_count = _inspect_input(args.matches)

    total, restored, missing, searched_roots = _restore_missing_word_crops(args.matches, args.library)
    if total:
        available = total - len(missing)
        print(
            f"v18: atlas word crops total={total}; available={available}; "
            f"restored={restored}; still_missing={len(missing)}"
        )
        if missing:
            for rel in missing[:12]:
                print(f"  missing: {rel}")
        if available == 0:
            roots = ", ".join(searched_roots) or "(none)"
            raise SystemExit(
                "v18: none of the atlas word crops are available, so the editor "
                "would generate 0 cards. Searched under: " + roots + "\n"
                "The atlas contains annotations, but the corresponding PNG word "
                "crops must be regenerated or copied back before resuming it."
            )

    rc = v17.main()
    if rc:
        return rc

    try:
        text = args.out.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"v18: output HTML missing: {exc}")
    cards = text.count('<article class="card"')
    if (word_count or result_count) and cards == 0:
        raise SystemExit(
            "v18: valid input generated 0 review cards. This is an editor conversion "
            "or word-image resolution bug, not valid empty input."
        )
    text = text.replace("SAOL live-lärande pixelannotering v17", "SAOL live-lärande pixelannotering v18", 1)
    text = text.replace("SAOL live-lärande pixelannotering v10", "SAOL live-lärande pixelannotering v18", 1)
    text = text.replace("corrected-v17.json", "corrected-v18.json")
    args.out.write_text(text, encoding="utf-8")
    print(f"v18: generated {cards} review cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
