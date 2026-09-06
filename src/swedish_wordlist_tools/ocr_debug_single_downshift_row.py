from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .ocr_find_unreviewed_glyph_rows import load_facit_with_typography
from .ocr_glyph_gap_matcher import max_internal_blank_run, safe_ink_groups
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)
from .ocr_single_downshift_safe_islands_benchmark import (
    _exact_solution_at_baseline,
    _first_island_solutions,
)


def _text(matches) -> str:
    return "".join(match.label for match in sorted(matches or [], key=lambda m: (m.x, m.baseline)))


def _ink_crop_from_state(state: dict) -> Image.Image:
    width = int(state["crop_width"])
    height = int(state["crop_height"])
    image = Image.new("L", (width, height), 255)
    pixels = image.load()
    for x, y in state.get("source_ink_points") or []:
        pixels[int(x), int(y)] = 0
    return image


def _print_plan(groups, crop_height: int, models, base: int, first_selected) -> None:
    print(f"plan: provar baslinje B={base}")
    print(
        f"  island 0 x={groups[0][0]}..{groups[0][1]} baseline={base} "
        f"OK text={_text(first_selected)!r}"
    )
    shifted = False
    for index, (left, right, local_ink) in enumerate(groups[1:], start=1):
        wanted = base + (1 if shifted else 0)
        selected, candidates = _exact_solution_at_baseline(
            local_ink,
            int(right) - int(left),
            crop_height,
            models,
            wanted,
        )
        if selected is not None:
            print(
                f"  island {index} x={left}..{right} baseline={wanted} "
                f"OK candidates={candidates} text={_text(selected)!r}"
            )
            continue

        print(
            f"  island {index} x={left}..{right} baseline={wanted} "
            f"MISS candidates={candidates}"
        )
        if shifted:
            print("  RESULTAT: MISS efter redan använd sänkning")
            return

        selected2, candidates2 = _exact_solution_at_baseline(
            local_ink,
            int(right) - int(left),
            crop_height,
            models,
            base + 1,
        )
        if selected2 is None:
            print(
                f"  island {index} x={left}..{right} baseline={base + 1} "
                f"MISS candidates={candidates2}"
            )
            print("  RESULTAT: MISS även efter tillåten B+1-sänkning")
            return
        shifted = True
        print(
            f"  island {index} x={left}..{right} baseline={base + 1} "
            f"OK candidates={candidates2} text={_text(selected2)!r}  <-- SÄNKNING LÅSES HÄR"
        )

    print(
        "  RESULTAT: EXAKT med "
        + ("en permanent B+1-sänkning" if shifted else "oförändrad baseline")
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Diagnostisera en SAOL-rad: visa den vanliga parserns resultat och "
            "prova den strikta engångssänkningen B -> B+1 ö för ö. Inget sparas."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    position = (args.column, args.row)
    state = load_review_state_pixel_array(context, position, models)

    print("=== VANLIG SCANNER/EDITOR ===")
    print(
        f"page={args.page} column={args.column} row={args.row} "
        f"crop_box={tuple(state['crop_box'])} baseline={state.get('baseline')} "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"fully_exact={state.get('fully_exact')} text={state.get('text', '')!r}"
    )
    print(f"exact_cover_path={state.get('exact_cover_path')!r}")

    crop = _ink_crop_from_state(state)
    ink = {(int(x), int(y)) for x, y in state.get("source_ink_points") or []}
    internal_gap = max_internal_blank_run(models)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)

    print("\n=== SÄKRA X-ÖAR ===")
    print(f"max_internal_blank_run={internal_gap} islands={len(groups)}")
    for index, (left, right, local_ink) in enumerate(groups):
        print(f"island {index}: x={left}..{right} width={right-left} pixels={len(local_ink)}")

    if not groups:
        print("Ingen säker x-ö hittades; single-downshift-regeln kan inte användas.")
        return 1

    first_left, first_right, first_ink = groups[0]
    first_solutions, first_candidates = _first_island_solutions(
        first_ink,
        int(first_right) - int(first_left),
        crop.height,
        models,
    )

    print("\n=== FÖRSTA ÖNS MÖJLIGA BASELINES ===")
    print(f"candidate_count={first_candidates}")
    if not first_solutions:
        print("Första ön har ingen exakt glyphlösning på någon baseline.")
        return 1
    for baseline, selected in sorted(first_solutions.items()):
        print(f"baseline={baseline} text={_text(selected)!r} glyphs={len(selected)}")

    print("\n=== STRICT B -> B+1 ===")
    for baseline, first_selected in sorted(first_solutions.items()):
        _print_plan(groups, crop.height, models, int(baseline), first_selected)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
