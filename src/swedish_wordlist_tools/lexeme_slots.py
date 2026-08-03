from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Mapping


@dataclass(frozen=True)
class SlotForm:
    """One written form assigned to a grammatical slot.

    ``source`` records the SAOL token or metadata that produced the form.  The
    representation is deliberately independent of word class: noun, verb and
    adjective interpreters can all emit the same objects with different slot
    names.
    """

    slot: str
    written_form: str
    source: str


@dataclass(frozen=True)
class LexemeSlots:
    """Word-class-independent intermediate representation for one lexeme."""

    lemma: str
    upos: str
    notation: str
    forms: tuple[SlotForm, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def forms_for(self, slot: str) -> tuple[str, ...]:
        """Return all distinct forms in ``slot`` while preserving source order."""
        seen: set[str] = set()
        result: list[str] = []
        for form in self.forms:
            if form.slot != slot or form.written_form in seen:
                continue
            seen.add(form.written_form)
            result.append(form.written_form)
        return tuple(result)

    def first(self, slot: str) -> str | None:
        forms = self.forms_for(slot)
        return forms[0] if forms else None

    def written_forms(self, *, include_lemma: bool = True) -> tuple[str, ...]:
        """Return all distinct written forms across slots."""
        seen: set[str] = set()
        result: list[str] = []
        for form in self.forms:
            if not include_lemma and form.slot == "lemma":
                continue
            if form.written_form in seen:
                continue
            seen.add(form.written_form)
            result.append(form.written_form)
        return tuple(result)

    def slots(self) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for form in self.forms:
            if form.slot in seen:
                continue
            seen.add(form.slot)
            result.append(form.slot)
        return tuple(result)

    def iter_slot(self, slot: str) -> Iterator[SlotForm]:
        return (form for form in self.forms if form.slot == slot)


def build_lexeme_slots(
    *,
    lemma: str,
    upos: str,
    notation: str,
    forms: Iterable[SlotForm],
    metadata: Mapping[str, str] | None = None,
) -> LexemeSlots:
    """Build a deduplicated immutable slot representation."""
    seen: set[tuple[str, str]] = set()
    unique: list[SlotForm] = []
    for form in forms:
        marker = (form.slot, form.written_form)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(form)
    if ("lemma", lemma) not in seen:
        unique.insert(0, SlotForm("lemma", lemma, "lemma"))
    return LexemeSlots(
        lemma=lemma,
        upos=upos.upper(),
        notation=notation,
        forms=tuple(unique),
        metadata=dict(metadata or {}),
    )
