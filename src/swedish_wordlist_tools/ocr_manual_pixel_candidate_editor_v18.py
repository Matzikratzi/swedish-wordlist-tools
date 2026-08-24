from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v17 as v17


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
        # Exact relative path in sibling harvest directories is preferred.
        for sibling in root.iterdir() if root.exists() else []:
            if not sibling.is_dir() or sibling == library:
                continue
            p = sibling / rel
            if p.exists():
                candidates.append(p)
        # Older editor runs sometimes put the crop directly in /tmp.
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
    if total and cards == 0:
        raise SystemExit(
            "v18: atlas loaded but generated 0 review cards even though word crops "
            "were found. This is an editor conversion bug, not a missing-file issue."
        )
    text = text.replace("SAOL live-lärande pixelannotering v17", "SAOL live-lärande pixelannotering v18", 1)
    text = text.replace("SAOL live-lärande pixelannotering v10", "SAOL live-lärande pixelannotering v18", 1)
    text = text.replace("corrected-v17.json", "corrected-v18.json")
    args.out.write_text(text, encoding="utf-8")
    print(f"v18: generated {cards} review cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
