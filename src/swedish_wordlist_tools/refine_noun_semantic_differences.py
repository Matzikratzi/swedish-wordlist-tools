from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl
from .saol_notation import FormOperationKind, parse_form_operations, split_alternative_branches

DEFAULT_COMPARISON = Path("reports/saol14-noun-forms-comparison.jsonl")
DEFAULT_JSON = Path("reports/saol14-noun-semantic-review.json")
DEFAULT_TEXT = Path("reports/saol14-noun-semantic-review.txt")


def _clean_stycke(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return value.replace("·", "").replace(".", "").casefold()


def _metadata_key(value: str) -> str:
    value = value.strip().strip("()")
    if value.endswith((":", ".")):
        value = value[:-1]
    return re.sub(r"[^0-9a-zåäöéü-]+", "", value.casefold())


def _notation_tokens(row: dict[str, Any]) -> tuple[str, ...]:
    branches = split_alternative_branches(str(row.get("notation", "")))
    return tuple(token for branch in branches for token in branch.tokens) if branches else ()


def _has_k_source_error(row: dict[str, Any]) -> bool:
    return "<k>" in str(row.get("notation", "")).casefold()


def _is_source_error_discarded_form(row: dict[str, Any], form: str) -> bool:
    if not _has_k_source_error(row):
        return False
    return bool(form) and form.casefold() != str(row.get("lemma", "")).casefold()


def _notation_metadata_forms(row: dict[str, Any]) -> frozenset[str]:
    result: set[str] = set()
    for token in _notation_tokens(row):
        raw = token.strip().strip("()")
        if not raw.startswith(("+", "-")) and raw.endswith((":", ".")):
            key = _metadata_key(raw)
            if key:
                result.add(key)
    return frozenset(result)


def _is_notation_metadata(row: dict[str, Any], form: str) -> bool:
    normalized = _metadata_key(form)
    return bool(normalized) and normalized in _notation_metadata_forms(row)


def _notation_markup_fragments(row: dict[str, Any]) -> frozenset[str]:
    notation = str(row.get("notation", ""))
    result: set[str] = set()
    for match in re.finditer(r"</?\s*([0-9A-Za-zÅÄÖåäöÉéÜü-]+)", notation):
        key = _metadata_key(match.group(1))
        if key:
            result.add(key)
    for token in _notation_tokens(row):
        raw = token.strip().strip("()")
        if raw.startswith(("+", "-")) or not raw.endswith("."):
            continue
        parts = [part for part in raw.split(".") if part]
        if len(parts) >= 2:
            result.update(key for part in parts if (key := _metadata_key(part)))
    return frozenset(result)


def _is_legacy_notation_markup(row: dict[str, Any], form: str) -> bool:
    normalized = _metadata_key(form)
    return bool(normalized) and normalized in _notation_markup_fragments(row)


def _notation_colon_fragments(row: dict[str, Any]) -> frozenset[str]:
    result: set[str] = set()
    for token in _notation_tokens(row):
        raw = token.strip().strip("()")
        if ":" in raw and not raw.endswith(":"):
            key = _metadata_key(raw.rsplit(":", 1)[1])
            if key:
                result.add(key)
    return frozenset(result)


def _is_legacy_colon_fragment(row: dict[str, Any], form: str) -> bool:
    if ":" in form:
        return False
    normalized = _metadata_key(form)
    return bool(normalized) and normalized in _notation_colon_fragments(row)


def _explicit_added_forms(row: dict[str, Any]) -> tuple[str, ...]:
    reasons = {
        str(key).casefold(): str(value)
        for key, value in row.get("change_reasons", {}).items()
    }
    return tuple(
        str(candidate)
        for candidate in row.get("added_forms", [])
        if reasons.get(str(candidate).casefold()) == "explicit"
    )


def _explicit_notation_forms(row: dict[str, Any]) -> tuple[str, ...]:
    """Read complete explicit forms directly from the shared notation parser."""

    result: list[str] = []
    for token in _notation_tokens(row):
        operations = parse_form_operations(token)
        if operations is None:
            continue
        for operation in operations:
            if operation.kind is FormOperationKind.EXPLICIT and operation.value not in result:
                result.append(operation.value)
    return tuple(result)


def _explicit_forms(row: dict[str, Any]) -> tuple[str, ...]:
    """Return explicit forms whether or not they are new in the comparison."""

    return tuple(dict.fromkeys((*_explicit_added_forms(row), *_explicit_notation_forms(row))))


def _legacy_replace_final_component(lemma: str, replacement: str) -> str | None:
    if not replacement:
        return None
    positions = [index for index, char in enumerate(lemma) if char == replacement[0]]
    return lemma[: positions[-1]] + replacement if positions else None


def _is_hyphenated_explicit_token_damage(old: str, lemma: str, explicit: str) -> bool:
    parts = explicit.split("-")
    if len(parts) < 2:
        return False
    return any(
        _legacy_replace_final_component(lemma, part) == old
        for part in parts[1:]
        if part
    )


def _is_legacy_explicit_form_error(row: dict[str, Any], form: str) -> bool:
    old = form.casefold()
    lemma = str(row.get("lemma", "")).casefold()
    if not old:
        return False
    for candidate in _explicit_forms(row):
        explicit = candidate.casefold()
        if old in {lemma, explicit}:
            continue
        if len(old) < len(explicit) and (
            explicit.startswith(old) or explicit.endswith(old)
        ):
            return True
        if lemma:
            for start in range(1, len(explicit)):
                if old == lemma + explicit[start:]:
                    return True
            if _is_hyphenated_explicit_token_damage(old, lemma, explicit):
                return True
    return False


def _is_stycke_guided_tail_error(row: dict[str, Any], form: str) -> bool:
    stycke = _clean_stycke(str(row.get("stycke", "")))
    if stycke.count("|") != 1:
        return False
    prefix, head = stycke.split("|", 1)
    lemma = str(row.get("lemma", "")).casefold()
    old = form.casefold()
    if not prefix or not head or prefix + head != lemma or not old:
        return False
    reasons = {
        str(key).casefold(): str(value)
        for key, value in row.get("change_reasons", {}).items()
    }
    correct_cut = len(prefix)
    for candidate in row.get("added_forms", []):
        candidate_folded = str(candidate).casefold()
        if reasons.get(candidate_folded) != "replace_tail":
            continue
        if candidate_folded == old or not candidate_folded.startswith(prefix):
            continue
        replacement = candidate_folded[correct_cut:]
        if not replacement:
            continue
        for wrong_cut in range(len(lemma) + 1):
            if wrong_cut != correct_cut and old == lemma[:wrong_cut] + replacement:
                return True
    return False


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left.casefold(), right.casefold()):
        if left_char != right_char:
            break
        length += 1
    return length


def _is_truncated_overflow_error(row: dict[str, Any], form: str) -> bool:
    notation = str(row.get("notation", ""))
    if len(notation) != 50:
        return False
    final_token = notation.rstrip().rsplit(maxsplit=1)[-1]
    if not final_token.endswith("-"):
        return False
    token_body = final_token[:-1].casefold()
    lemma = str(row.get("lemma", "")).casefold()
    old = form.casefold()
    if not token_body or not lemma or not old:
        return False
    shared = _common_prefix_length(lemma, old)
    if shared < max(1, len(lemma) - 1):
        return False
    extra = old[shared:]
    return bool(extra) and token_body.endswith(extra)


def classify_form(row: dict[str, Any], form: str) -> str:
    if _is_source_error_discarded_form(row, form):
        return "source_error_discarded_form"
    if _is_legacy_notation_markup(row, form):
        return "legacy_notation_markup"
    if _is_notation_metadata(row, form):
        return "legacy_notation_metadata"
    if _is_legacy_colon_fragment(row, form):
        return "legacy_colon_fragment"
    # Field-boundary truncation is more specific than damage inferred from an
    # explicit form elsewhere in the same notation, so it must win precedence.
    if _is_truncated_overflow_error(row, form):
        return "legacy_truncated_overflow_error"
    if _is_legacy_explicit_form_error(row, form):
        return "legacy_explicit_form_error"
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
        reason_counts.update(classifications.values())
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
        f"Källfelsformer bortvalda enligt lemma-only-policy: {counts.get('source_error_discarded_form', 0)}",
        f"Verifierade markup-/etikettfragment: {counts.get('legacy_notation_markup', 0)}",
        f"Verifierad notationsmetadata: {counts.get('legacy_notation_metadata', 0)}",
        f"Verifierade kolonfragment: {counts.get('legacy_colon_fragment', 0)}",
        f"Verifierade explicita formfel: {counts.get('legacy_explicit_form_error', 0)}",
        f"Verifierade stycke-styrda tail-fel: {counts.get('legacy_stycke_tail_error', 0)}",
        f"Verifierade avhuggningsfel vid fältgränsen: {counts.get('legacy_truncated_overflow_error', 0)}",
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
