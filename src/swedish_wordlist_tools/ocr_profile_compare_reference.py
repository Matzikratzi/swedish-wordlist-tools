from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_profile(path: Path) -> dict[int, dict]:
    pages = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                page = json.loads(line)
                pages[int(page["page"])] = page
    return pages


def _load_reference(path: Path) -> dict[tuple[int, int], dict]:
    rows = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows[(int(row["column"]), int(row["row"]))] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile_jsonl", type=Path)
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=20)
    parser.add_argument("--show", type=int, default=50)
    args = parser.parse_args()

    pages = _load_profile(args.profile_jsonl)
    total_ref = total_profile = exact = text_mismatches = missing = extra = 0
    details: list[str] = []

    for page_number in range(args.start_page, args.end_page + 1):
        ref_path = args.reference_dir / f"page-{page_number:03d}.jsonl"
        if not ref_path.exists():
            details.append(f"page={page_number}: MISSING_REFERENCE")
            continue
        reference = _load_reference(ref_path)
        profile_page = pages.get(page_number)
        if profile_page is None:
            details.append(f"page={page_number}: MISSING_PROFILE_PAGE")
            missing += len(reference)
            total_ref += len(reference)
            continue

        profile = {}
        for column in profile_page.get("columns", []):
            col = int(column["column"])
            for row in column.get("rows", []):
                profile[(col, int(row["index"]))] = row

        total_ref += len(reference)
        total_profile += len(profile)
        for key in sorted(reference.keys() | profile.keys()):
            ref = reference.get(key)
            got = profile.get(key)
            col, row = key
            if ref is None:
                extra += 1
                details.append(
                    f"page={page_number} col={col} row={row}: EXTRA profile={got.get('text', '')!r}"
                )
                continue
            if got is None:
                missing += 1
                details.append(
                    f"page={page_number} col={col} row={row}: MISSING reference={ref.get('text', '')!r}"
                )
                continue
            ref_text = str(ref.get("text") or "")
            got_text = str(got.get("text") or "")
            if ref_text == got_text:
                exact += 1
            else:
                text_mismatches += 1
                ref_labels = "".join(str(g.get("label") or "") for g in ref.get("glyphs", []))
                got_labels = "".join(str(g.get("label") or "") for g in got.get("matches", []))
                details.append(
                    f"page={page_number} col={col} row={row}: TEXT_MISMATCH\n"
                    f"  reference_text={ref_text!r}\n"
                    f"  profile_text  ={got_text!r}\n"
                    f"  reference_glyphs={ref_labels!r}\n"
                    f"  profile_glyphs  ={got_labels!r}"
                )

    print(
        "profile-reference-summary: "
        f"pages={args.start_page}..{args.end_page} "
        f"reference_rows={total_ref} profile_rows={total_profile} "
        f"exact_text_rows={exact} text_mismatches={text_mismatches} "
        f"missing_rows={missing} extra_rows={extra}"
    )
    for detail in details[: args.show]:
        print(detail)
    if len(details) > args.show:
        print(f"... {len(details) - args.show} more differences")
    return 0 if not (text_mismatches or missing or extra) else 1


if __name__ == "__main__":
    raise SystemExit(main())
