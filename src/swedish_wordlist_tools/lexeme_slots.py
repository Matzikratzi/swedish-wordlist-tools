from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Mapping


@dataclass(frozen=True)
class SlotForm:
    """One written form assigned to a grammatical slot.

    ``source`` keeps the concrete token or rule that produced the form for
    backwards compatibility. ``provenance`` records the source layer so row
    interpretation, compound-head repair and external fallback remain
    distinguishable. ``provenance_detail`` stores a stable source identifier,
    such as a SALDO lexeme id or the borrowed head lemma.
    """

    slot: str
    written_form: str
    source: str
    provenance: str = "row"
    provenance_detail: str = ""


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

    def provenance_counts(self) -> dict[str, int]:
        """Count distinct slot/form pairs by provenance layer."""
        counts: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for form in self.forms:
            marker = (form.slot, form.written_form)
            if marker in seen:
                continue
            seen.add(marker)
            counts[form.provenance] = counts.get(form.provenance, 0) + 1
        return counts


def build_lexeme_slots(
    *,
    lemma: str,
    upos: str,
    notation: str,
    forms: Iterable[SlotForm],
    metadata: Mapping[str, str] | None = None,
) -> LexemeSlots:
    """Build a deduplicated immutable slot representation.

    Earlier forms win when the same slot/form pair occurs from several layers.
    Callers should therefore append fallbacks after row-derived evidence.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[SlotForm] = []
    for form in forms:
        marker = (form.slot, form.written_form)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(form)
    if ("lemma", lemma) not in seen:
        unique.insert(0, SlotForm("lemma", lemma, "lemma", "row", "lemma"))
    return LexemeSlots(
        lemma=lemma,
        upos=upos.upper(),
        notation=notation,
        forms=tuple(unique),
        metadata=dict(metadata or {}),
    )
