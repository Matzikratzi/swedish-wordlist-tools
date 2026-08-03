from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_SUP_RE = re.compile(r"<sup>.*?</sup>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SEPARATORS_RE = re.compile(r"[·\u00b7]")


def clean_stycke(value: object) -> str:
    """Return lexical spelling from SAOL ``stycke`` markup."""
    text = html.unescape(str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return _SEPARATORS_RE.sub("", text).strip()


def compound_verb_parts(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """Return ``(prefix, head, trailing_words)`` for an exact bar-marked verb.

    Only the last bar is significant.  The cleaned first word must equal the
    target lemma's first word, so malformed or merely typographical bars are
    never used as evidence.
    """
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


def build_simple_verb_paradigm_index(
    records: Iterable[Mapping[str, Any]],
    interpreted: Mapping[int, LexemeSlots | None],
) -> dict[str, LexemeSlots]:
    """Index unbarred, independently interpreted verbs by exact lemma.

    Ambiguous lemmas with differing paradigms are omitted instead of guessed.
    ``interpreted`` is keyed by ``id(record)`` so duplicate source rows remain
    distinct while the index is built.
    """
    candidates: dict[str, list[LexemeSlots]] = {}
    for record in records:
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        if "|" in clean_stycke(record.get("stycke")):
            continue
        slots = interpreted.get(id(record))
        if slots is None:
            continue
        lemma = str(record.get("normaliserat_ord") or "").strip()
        if lemma:
            candidates.setdefault(lemma, []).append(slots)

    result: dict[str, LexemeSlots] = {}
    for lemma, rows in candidates.items():
        signatures = {
            tuple((form.slot, form.written_form) for form in row.forms)
            for row in rows
        }
        if len(signatures) == 1:
            result[lemma] = rows[0]
    return result


def borrow_compound_verb_slots(
    record: Mapping[str, Any],
    base_by_lemma: Mapping[str, LexemeSlots],
    current: LexemeSlots | None = None,
) -> LexemeSlots | None:
    """Fill a bar-marked compound from an exact independent head verb.

    Existing target slots win.  Borrowing only fills missing slots and never
    invents a paradigm when the exact right-hand verb is absent or ambiguous.
    """
    parts = compound_verb_parts(record)
    if parts is None:
        return current
    prefix, head, trailing_words = parts
    source = base_by_lemma.get(head)
    if source is None:
        return current

    lemma = str(record.get("normaliserat_ord") or "").strip()
    forms = list(current.forms if current is not None else ())
    existing_slots = {form.slot for form in forms}
    if not forms:
        forms.append(SlotForm("infinitive", lemma, "lemma"))
        existing_slots.add("infinitive")

    borrowed = False
    for form in source.forms:
        if form.slot in {"lemma", "infinitive"} or form.slot in existing_slots:
            continue
        if not form.written_form.startswith(head):
            continue
        suffix = form.written_form[len(head) :]
        written = prefix + head + suffix + trailing_words
        forms.append(SlotForm(form.slot, written, f"compound-head:{head}"))
        borrowed = True

    if not borrowed:
        return current
    metadata = dict(current.metadata if current is not None else {})
    metadata.update({
        "compound_head": head,
        "compound_head_source": source.lemma,
        "stycke": str(record.get("stycke") or ""),
        "ordkl": str(record.get("ordkl") or ""),
    })
    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=current.notation if current is not None else str(record.get("text") or ""),
        forms=forms,
        metadata=metadata,
    )
