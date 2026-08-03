from __future__ import annotations

import html
from collections.abc import Iterable, Mapping
from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_TEXT_HARD_CAP = 50
_VERB_FORM_SLOTS = ("present", "preterite", "supine")


def clean_stycke(value: object) -> str:
    text = html.unescape(str(value or ""))
    while "<sup>" in text.lower():
        start = text.lower().find("<sup>")
        end = text.lower().find("</sup>", start)
        if end < 0:
            break
        text = text[:start] + text[end + len("</sup>") :]
    result: list[str] = []
    in_tag = False
    for char in text:
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag and char not in {"·", "\u00b7"}:
            result.append(char)
    return "".join(result).strip()


def compound_verb_parts(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    stycke = clean_stycke(record.get("stycke"))
    if "|" not in stycke:
        return None
    marked_first, _sep, _marked_rest = stycke.partition(" ")
    prefix, head = marked_first.rsplit("|", 1)
    lemma = str(record.get("normaliserat_ord") or "").strip()
    lemma_first, separator, trailing = lemma.partition(" ")
    if not prefix or not head or prefix + head != lemma_first:
        return None
    return prefix, head, separator + trailing if separator else ""


def _source_is_truncated(record: Mapping[str, Any]) -> bool:
    """The machine-readable ``text`` export has an observed hard cap at 50."""
    return len(str(record.get("text") or "")) == _TEXT_HARD_CAP


def _head_forms_from_compound(
    slots: LexemeSlots,
    *,
    prefix: str,
    trailing_words: str,
    slot: str,
) -> frozenset[str]:
    """Project compound forms back to the exact bar-marked head verb."""
    result: set[str] = set()
    for written in slots.forms_for(slot):
        without_trailing = written
        if trailing_words:
            if not written.endswith(trailing_words):
                continue
            without_trailing = written[: -len(trailing_words)]
        if not without_trailing.startswith(prefix):
            continue
        head_form = without_trailing[len(prefix) :]
        if head_form and " " not in head_form:
            result.add(head_form)
    return frozenset(result)


def build_simple_verb_paradigm_index(
    records: Iterable[Mapping[str, Any]],
    interpreted: Mapping[int, LexemeSlots | None],
) -> dict[str, LexemeSlots]:
    """Build exact head paradigms using only complete source evidence.

    An independent verb row proves that the head verb exists even when its
    ``text`` is ``(null)``. It contributes forms only when it has interpreted,
    non-truncated data. Complete bar-marked compounds may also prove head forms
    by removing their exact prefix. Rows at the observed 50-character cap never
    provide head-form evidence. Conflicting complete evidence excludes the
    entire head verb instead of guessing.
    """
    record_list = list(records)
    independent_heads: set[str] = set()
    evidence: dict[str, dict[str, list[frozenset[str]]]] = {}

    def add_evidence(head: str, slot: str, forms: frozenset[str]) -> None:
        if forms:
            evidence.setdefault(head, {}).setdefault(slot, []).append(forms)

    for record in record_list:
        if str(record.get("upos", "")).upper() != "VERB":
            continue

        parts = compound_verb_parts(record)
        if parts is None:
            lemma = str(record.get("normaliserat_ord") or "").strip()
            if lemma and " " not in lemma:
                independent_heads.add(lemma)

        slots = interpreted.get(id(record))
        if slots is None or _source_is_truncated(record):
            continue

        if parts is None:
            lemma = str(record.get("normaliserat_ord") or "").strip()
            if not lemma or " " in lemma:
                continue
            for slot in _VERB_FORM_SLOTS:
                add_evidence(lemma, slot, frozenset(slots.forms_for(slot)))
            continue

        prefix, head, trailing_words = parts
        for slot in _VERB_FORM_SLOTS:
            add_evidence(
                head,
                slot,
                _head_forms_from_compound(
                    slots,
                    prefix=prefix,
                    trailing_words=trailing_words,
                    slot=slot,
                ),
            )

    result: dict[str, LexemeSlots] = {}
    for head, slot_evidence in evidence.items():
        if head not in independent_heads:
            continue

        chosen_by_slot: dict[str, frozenset[str]] = {}
        ambiguous = False
        for slot in _VERB_FORM_SLOTS:
            candidates = [forms for forms in slot_evidence.get(slot, []) if forms]
            if not candidates:
                continue
            distinct = set(candidates)
            if len(distinct) != 1:
                ambiguous = True
                break
            chosen_by_slot[slot] = candidates[0]

        if ambiguous or not chosen_by_slot:
            continue

        forms: list[SlotForm] = [SlotForm("infinitive", head, "lemma")]
        for slot in _VERB_FORM_SLOTS:
            for written in sorted(chosen_by_slot.get(slot, ())):
                forms.append(SlotForm(slot, written, "complete-verb-family-evidence"))
        result[head] = build_lexeme_slots(
            lemma=head,
            upos="VERB",
            notation="complete-head-family-evidence",
            forms=forms,
            metadata={"head_evidence": "complete-independent-or-bar-family"},
        )
    return result


def _can_replace_truncated_form(
    existing: str,
    borrowed: str,
    *,
    source_is_truncated: bool,
) -> bool:
    return (
        source_is_truncated
        and existing != borrowed
        and borrowed.startswith(existing)
    )


def borrow_compound_verb_slots(
    record: Mapping[str, Any],
    base_by_lemma: Mapping[str, LexemeSlots],
    current: LexemeSlots | None = None,
) -> LexemeSlots | None:
    parts = compound_verb_parts(record)
    if parts is None:
        return current
    prefix, head, trailing_words = parts
    source = base_by_lemma.get(head)
    if source is None:
        return current

    lemma = str(record.get("normaliserat_ord") or "").strip()
    forms = list(current.forms if current is not None else ())
    if not forms:
        forms.append(SlotForm("infinitive", lemma, "lemma"))

    source_is_truncated = _source_is_truncated(record)
    changed = False
    for source_form in source.forms:
        if source_form.slot in {"lemma", "infinitive"}:
            continue
        source_first, separator, source_trailing = source_form.written_form.partition(" ")
        if separator or source_trailing:
            continue
        borrowed = prefix + source_first + trailing_words

        same_slot = [form for form in forms if form.slot == source_form.slot]
        if not same_slot:
            forms.append(SlotForm(source_form.slot, borrowed, f"compound-head:{head}"))
            changed = True
            continue

        replaceable = [
            form
            for form in same_slot
            if _can_replace_truncated_form(
                form.written_form,
                borrowed,
                source_is_truncated=source_is_truncated,
            )
        ]
        if not replaceable:
            continue
        replaceable_ids = {id(form) for form in replaceable}
        forms = [form for form in forms if id(form) not in replaceable_ids]
        forms.append(
            SlotForm(source_form.slot, borrowed, f"compound-head-repair:{head}")
        )
        changed = True

    if not changed:
        return current
    metadata = dict(current.metadata if current is not None else {})
    metadata.update(
        {
            "compound_head": head,
            "compound_head_source": source.lemma,
            "stycke": str(record.get("stycke") or ""),
            "ordkl": str(record.get("ordkl") or ""),
        }
    )
    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=(
            current.notation
            if current is not None
            else str(record.get("text") or "")
        ),
        forms=forms,
        metadata=metadata,
    )
