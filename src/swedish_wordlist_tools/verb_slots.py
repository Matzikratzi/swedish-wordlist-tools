from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_row_interpreter import apply_form_token

_FORM_TOKEN_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_MARKER_RE = re.compile(
    r"(?:\bel\.|\bvard\.|\båld\.|\bprov\.|\bibl\.|\bn\.|\bH\b)",
    re.IGNORECASE,
)
_PRESENT_RE = re.compile(r"\bpres\.\s*", re.IGNORECASE)
_NO_INFLECTION_RE = re.compile(r"^\s*(?:ingen\s*:?[ ]*böjning\s*:?)\s*$", re.IGNORECASE)


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
    tokens = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(cleaned))
    ignored = {"el", "vard", "åld", "prov", "ibl", "n", "h"}
    return tuple(token for token in tokens if token.casefold() not in ignored)


def _first_group(text: str) -> str:
    return re.split(r"[,;]", text, maxsplit=1)[0].strip()


def _labelled_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    match = _PRESENT_RE.search(pattern)
    if match is None:
        return None
    before = pattern[: match.start()].strip(" ,;:")
    after = pattern[match.end() :].strip()
    groups = [part.strip() for part in before.split(",") if part.strip()]
    if len(groups) < 2:
        return None

    assignments: list[tuple[str, str]] = []
    for slot, group in (("preterite", groups[0]), ("supine", groups[1])):
        alternatives = _alternative_tokens(group)
        if not alternatives:
            return None
        assignments.extend((slot, token) for token in alternatives)

    present = _alternative_tokens(_first_group(after))
    if not present:
        return None
    assignments.extend(("present", token) for token in present)
    return tuple(assignments)


def _simple_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    tokens = _tokens(pattern)
    if tokens is None or len(tokens) not in {2, 3}:
        return None
    if len(tokens) == 2:
        return (("preterite", tokens[0]), ("supine", tokens[1]))
    return (("present", tokens[0]), ("preterite", tokens[1]), ("supine", tokens[2]))


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
    variants = tuple(part.strip() for part in re.split(r"\s+_\s+", pattern) if part.strip())
    if not variants:
        return "no_variants"
    for variant in variants:
        assignments = _labelled_assignments(variant)
        if assignments is None:
            assignments = _simple_assignments(variant)
        if assignments is None:
            if _PRESENT_RE.search(variant):
                return "labelled_syntax_unparsed"
            return "simple_syntax_unparsed"
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
    }
    if _NO_INFLECTION_RE.fullmatch(pattern):
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation=pattern,
            forms=(SlotForm("infinitive", lemma, "lemma"),),
            metadata=metadata,
        )

    forms = [SlotForm("infinitive", lemma, "lemma")]
    for variant in (part.strip() for part in re.split(r"\s+_\s+", pattern) if part.strip()):
        assignments = _labelled_assignments(variant) or _simple_assignments(variant)
        assert assignments is not None
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
