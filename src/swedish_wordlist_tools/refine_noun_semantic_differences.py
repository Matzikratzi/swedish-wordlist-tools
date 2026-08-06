from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_notation import split_alternative_branches

DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-comparison.jsonl")
DEFAULT_JSON = Path("reports/saol14-noun-semantic-review.json")
DEFAULT_TEXT = Path("reports/saol14-noun-semantic-review.txt")


def _clean_stycke(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return value.replace("·", "").replace(".", "").casefold()


def _metadata_key(value: str) -> str:
    """Normalize one notation metadata token like ``(mest:`` or ``ibl.``."""

    value = value.strip().strip("()")
    if value.endswith((":", ".")):
        value = value[:-1]
    return re.sub(r"[^0-9a-zåäöéü-]+", "", value.casefold())


def _notation_metadata_forms(row: dict[str, Any]) -> frozenset[str]:
    """Return comment words and period-final labels from the row notation.

    The vocabulary is derived from SAOL's syntax in the current row. No list of
    Swedish comment words is maintained here: a token ending in ``:`` is
    explanatory prose, and a token ending in ``.`` is a label.
    """

    notation = str(row.get("notation", ""))
    branches = split_alternative_branches(notation)
    if not branches:
        return frozenset()

    result: set[str] = set()
    for branch in branches:
        for token in branch.tokens:
            raw = token.strip().strip("()")
            if raw.startswith(("+", "-")):
                continue
            if raw.endswith((":", ".")):
                key = _metadata_key(raw)
                if key:
                    result.add(key)
    return frozenset(result)


def _is_notation_metadata(row: dict[str, Any], form: str) -> bool:
    normalized = _metadata_key(form)
    return bool(normalized) and normalized in _notation_metadata_forms(row)


def _is_stycke_guided_tail_error(row: dict[str, Any], form: str) -> bool:
    stycke = _clean_stycke(str(row.get("stycke", "")))
    if "|" not in stycke:
        return False
    prefix = stycke.rsplit("|", 1)[0]
    lemma = str(row.get("lemma", "")).casefold()
    old = form.casefold()
    if not prefix or not lemma or not old.startswith(lemma):
        return False

    reasons = {
        str(key).casefold(): str(value)
        for key, value in row.get("change_reasons", {}).items()
    }
    for candidate in row.get("added_forms", []):
        candidate_folded = str(candidate).casefold()
        if reasons.get(candidate_folded) != "replace_tail":
            continue
        if not candidate_folded.startswith(prefix):
            continue
        tail = candidate_folded[len(prefix):]
        if tail and old in {lemma + tail, lemma + tail[1:]}:
            return True
    return False


def classify_form(row: dict[str, Any], form: str) -> str:
    if _is_notation_metadata(row, form):
        return "legacy_notation_metadata"
    if _is_stycke_guided_tail_error(row, form):
        return "legacy_stycke_tail_error"
    return "review_required"


def build_review(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reviewed: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    notation_counts: Counter[str] = Counter()

    for row in rows:
        forms = [str(form) for form in row.get("semantic_removed_forms", [])]
        if not forms:
            continue
        classifications = {form: classify_form(row, form) for form in forms}
        candidates = [
            form for form, reason in classifications.items() if reason == "review_required"
        ]
        for reason in classifications.values():
            reason_counts[reason] += 1
        if candidates:
            notation_counts[str(row.get("notation", ""))] += 1
        reviewed.append(
            {
                "record_id": row.get("record_id", ""),
                "lemma": row.get("lemma", ""),
                "notation": row.get("notation", ""),
                "stycke": row.get("stycke", ""),
                "classifications": classifications,
                "review_required_forms": candidates,
                "added_forms": row.get("added_forms", []),
                "change_reasons": row.get("change_reasons", {}),
            }
        )

    review_rows = [row for row in reviewed if row["review_required_forms"]]
    review_rows.sort(
        key=lambda row: (
            -notation_counts[str(row["notation"])],
            str(row["notation"]).casefold(),
            str(row["lemma"]).casefold(),
        )
    )
    return {
        "semantic_rows": len(reviewed),
        "semantic_forms": sum(len(row["classifications"]) for row in reviewed),
        "classification_counts": dict(sorted(reason_counts.items())),
        "review_required_rows": len(review_rows),
        "review_required_forms": sum(
            len(row["review_required_forms"]) for row in review_rows
        ),
        "review_notation_groups": [
            {"notation": notation, "count": count}
            for notation, count in sorted(
                notation_counts.items(), key=lambda item: (-item[1], item[0].casefold())
            )
        ],
        "rows": review_rows,
    }


def render_review(review: dict[str, Any]) -> str:
    counts = review["classification_counts"]
    lines = [
        f"Semantiska poster före förfining: {review['semantic_rows']}",
        f"Semantiska former före förfining: {review['semantic_forms']}",
        f"Verifierad notationsmetadata: {counts.get('legacy_notation_metadata', 0)}",
        f"Verifierade stycke-styrda tail-fel: {counts.get('legacy_stycke_tail_error', 0)}",
        f"Poster kvar för granskning: {review['review_required_rows']}",
        f"Former kvar för granskning: {review['review_required_forms']}",
        "",
        "Största kvarvarande notationsgrupper:",
    ]
    for group in review["review_notation_groups"][:30]:
        lines.append(f"  {group['count']:4}  {group['notation']}")
    lines.extend(["", "Kvarvarande poster:"])
    for row in review["rows"]:
        forms = ", ".join(row["review_required_forms"])
        lines.append(
            f"  {row['lemma']} | {row['notation']} | stycke={row['stycke']} | {forms}"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refine noun semantic differences using shared SAOL notation structure"
    )
    parser.add_argument("comparison", nargs="?", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    review = build_review(read_jsonl(args.comparison))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.text.write_text(render_review(review), encoding="utf-8")
    print(f"Poster kvar för granskning: {review['review_required_rows']}")
    print(f"Former kvar för granskning: {review['review_required_forms']}")
    print(f"Rapport: {args.text}")


if __name__ == "__main__":
    main()
