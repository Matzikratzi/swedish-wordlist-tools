from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_SUP_RE = re.compile(r"<sup>.*?</sup>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SEPARATORS_RE = re.compile(r"[·\u00b7]")
_TRUNCATION_MARK_RE = re.compile(r"(?:\.\.\.|…)")


def clean_stycke(value: object) -> str:
    """Return lexical spelling from SAOL ``stycke`` markup."""
    text = html.unescape(str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return _SEPARATORS_RE.sub("", text).strip()


def compound_verb_parts(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """Return ``(prefix, head, trailing_words)`` for an exact bar-marked verb."""
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
    """Index unbarred, independently interpreted verbs by exact lemma."""
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


def _source_is_truncated(record: Mapping[str, Any]) -> bool:
    return bool(
        _TRUNCATION_MARK_RE.search(str(record.get("ordkl") or ""))
        or _TRUNCATION_MARK_RE.search(str(record.get("text") or ""))
    )


def _can_replace_truncated_form(
    existing: str,
    borrowed: str,
    *,
    source_is_truncated: bool,
) -> bool:
    """Return true only when ``existing`` is a strict prefix of ``borrowed``.

    This repairs source rows such as ``pres. -skr`` -> ``avskriver`` while
    preserving complete target-specific alternatives. The source must carry an
    explicit ellipsis marker, so ordinary short forms are never replaced.
    """
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
    """Fill or repair a bar-marked compound from an exact head verb.

    Complete existing target forms win. A source-truncated form may be replaced
    only when it is a strict prefix of the form borrowed from the independent
    head verb.
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
            forms.append(
                SlotForm(source_form.slot, borrowed, f"compound-head:{head}")
            )
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
