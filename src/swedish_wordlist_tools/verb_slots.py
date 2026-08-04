from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_row_interpreter import apply_form_token

_TEXT_HARD_CAP = 50
_FORM_TOKEN_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_MARKER_RE = re.compile(
    r"(?:\bel\.|\bvard\.|\båld\.|\bprov\.|\bibl\.|\bn\.|\bH\b)",
    re.IGNORECASE,
)
_PRESENT_RE = re.compile(r"\bpres\.\s*", re.IGNORECASE)
_TRUNCATED_PRESENT_RE = re.compile(r"(?:[,;]\s*)?\bpre(?:s\.?)?\s*$", re.IGNORECASE)
_NO_INFLECTION_RE = re.compile(r"^\s*(?:ingen\s*:?[ ]*böjning\s*:?)\s*$", re.IGNORECASE)
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")


def _source_is_truncated(record: dict[str, Any]) -> bool:
    """Return true at the observed hard cap of the SAOL ``text`` export."""
    return len(str(record.get("text") or "")) == _TEXT_HARD_CAP


def _drop_unterminated_final_token(
    assignments: tuple[tuple[str, str], ...],
    variant: str,
    *,
    source_is_truncated: bool,
) -> tuple[tuple[str, str], ...]:
    """Discard the final form token when a source row ends at the hard cap.

    At exactly 50 characters the export may have cut the row in the middle of
    a form without an ellipsis.  Earlier comma/semicolon-delimited groups are
    still trustworthy, but the token reaching the end of the field is not.
    Remove only the last matching assignment, preserving all earlier forms.
    """
    if not source_is_truncated or not assignments:
        return assignments
    matches = tuple(_FORM_TOKEN_RE.finditer(variant))
    if not matches or matches[-1].end() != len(variant):
        return assignments
    final_token = matches[-1].group(0)
    result = list(assignments)
    for index in range(len(result) - 1, -1, -1):
        if result[index][1] == final_token:
            del result[index]
            break
    return tuple(result)


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left.casefold(), right.casefold()):
        if left_char != right_char:
            break
        length += 1
    return length


def _replace_verb_final_component(lemma: str, replacement: str) -> str | None:
    first, separator, rest = lemma.partition(" ")
    best_start: int | None = None
    best_shared = 0
    for start in range(len(first)):
        candidate = first[start:]
        shared = _common_prefix_length(candidate, replacement)
        if shared > best_shared and len(candidate) >= 3:
            best_start = start
            best_shared = shared
    if best_start is None or best_shared < 1:
        return None
    result = first[:best_start] + replacement
    return result + (separator + rest if separator else "")


def _apply_token(record: dict[str, Any], lemma: str, token: str) -> str | None:
    first, separator, rest = lemma.partition(" ")
    if separator and token.startswith("-"):
        written_first = apply_form_token(record, first, token)
        if written_first is None:
            replacement = token[1:]
            written_first = (
                _replace_verb_final_component(first, replacement)
                if replacement
                else None
            )
        if written_first is not None:
            return written_first + separator + rest

    written = apply_form_token(record, lemma, token)
    if written is not None or not token.startswith("-"):
        return written
    replacement = token[1:]
    return _replace_verb_final_component(lemma, replacement) if replacement else None


def _tokens(pattern: str) -> tuple[str, ...] | None:
    matches = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(pattern))
    remainder = _FORM_TOKEN_RE.sub(" ", pattern)
    if remainder.strip():
        return None
    return matches or None


def _alternative_tokens(text: str) -> tuple[str, ...]:
    cleaned = _MARKER_RE.sub(" ", text)
    cleaned = _PAREN_COMMENT_RE.sub(" ", cleaned)
    tokens = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(cleaned))
    ignored = {"el", "vard", "åld", "prov", "ibl", "n", "h"}
    return tuple(token for token in tokens if token.casefold() not in ignored)


def _first_group(text: str) -> str:
    return re.split(r"[,;]", text, maxsplit=1)[0].strip()


def _first_two_group_assignments(text: str) -> tuple[tuple[str, str], ...] | None:
    groups = [part.strip() for part in text.split(",") if part.strip()]
    if len(groups) < 2:
        return None
    assignments: list[tuple[str, str]] = []
    for slot, group in (("preterite", groups[0]), ("supine", groups[1])):
        alternatives = _alternative_tokens(group)
        if not alternatives:
            return None
        assignments.extend((slot, token) for token in alternatives)
    return tuple(assignments)


def _labelled_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    match = _PRESENT_RE.search(pattern)
    if match is None:
        return None
    before = pattern[: match.start()].strip(" ,;:")
    after = pattern[match.end() :].strip()
    groups = [part.strip() for part in before.split(",") if part.strip()]

    assignments: list[tuple[str, str]] = []
    if len(groups) >= 2:
        first_two = _first_two_group_assignments(before)
        if first_two is None:
            return None
        assignments.extend(first_two)
    elif len(groups) == 1:
        compact = _alternative_tokens(groups[0])
        if len(compact) != 2:
            return None
        assignments.extend((
            ("preterite", compact[0]),
            ("supine", compact[1]),
        ))
    else:
        return None

    present = _alternative_tokens(_first_group(after))
    assignments.extend(("present", token) for token in present)
    return tuple(assignments)


def _truncated_label_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    match = _TRUNCATED_PRESENT_RE.search(pattern)
    if match is None:
        return None
    before = pattern[: match.start()].strip(" ,;:")
    return _first_two_group_assignments(before)


def _comma_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    groups = [part.strip() for part in pattern.split(",") if part.strip()]
    if len(groups) == 2 or (len(groups) > 2 and groups[0].startswith("-")):
        return _first_two_group_assignments(pattern)
    return None


def _simple_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    cleaned = _PAREN_COMMENT_RE.sub(" ", pattern)
    tokens = _tokens(cleaned)
    if tokens is None or len(tokens) not in {2, 3}:
        return None
    if len(tokens) == 2:
        return (("preterite", tokens[0]), ("supine", tokens[1]))
    return (("present", tokens[0]), ("preterite", tokens[1]), ("supine", tokens[2]))


def _assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    return (
        _labelled_assignments(pattern)
        or _truncated_label_assignments(pattern)
        or _comma_assignments(pattern)
        or _simple_assignments(pattern)
    )


def _record_variants(record: dict[str, Any], pattern: str) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    variants = tuple(part.strip() for part in re.split(r"\s+_\s+", pattern) if part.strip())
    if not variants:
        return None
    result: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    truncated = _source_is_truncated(record)
    for index, variant in enumerate(variants):
        assignments = _assignments(variant)
        if assignments is None:
            return None
        if truncated and index == len(variants) - 1:
            assignments = _drop_unterminated_final_token(
                assignments,
                variant,
                source_is_truncated=True,
            )
        result.append((variant, assignments))
    return tuple(result)


def diagnose_verb_record(record: dict[str, Any]) -> str:
    if str(record.get("upos", "")).upper() != "VERB":
        return "not_verb"
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return "missing_lemma"
    pattern = normalise_pattern(record.get("text"))
    if pattern is None:
        return "missing_pattern"
    if _NO_INFLECTION_RE.fullmatch(pattern):
        return "ok_no_inflection"
    parsed = _record_variants(record, pattern)
    if parsed is None:
        if _PRESENT_RE.search(pattern):
            return "labelled_syntax_unparsed"
        return "simple_syntax_unparsed"
    for _variant, assignments in parsed:
        for _slot, token in assignments:
            if _apply_token(record, lemma, token) is None:
                return "form_token_not_applied"
    return "ok"


def interpret_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    if diagnose_verb_record(record) not in {"ok", "ok_no_inflection"}:
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    assert pattern is not None

    metadata = {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "stycke": str(record.get("stycke") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "text_hard_cap": "true" if _source_is_truncated(record) else "false",
    }
    if _NO_INFLECTION_RE.fullmatch(pattern):
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation=pattern,
            forms=(SlotForm("infinitive", lemma, "lemma"),),
            metadata=metadata,
        )

    parsed = _record_variants(record, pattern)
    assert parsed is not None
    forms = [SlotForm("infinitive", lemma, "lemma")]
    for _variant, assignments in parsed:
        for slot, token in assignments:
            written_form = _apply_token(record, lemma, token)
            assert written_form is not None
            forms.append(SlotForm(slot, written_form, token))

    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=pattern,
        forms=forms,
        metadata=metadata,
    )
