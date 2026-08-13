from __future__ import annotations

import re
from typing import Any


def ordkl_head(record: dict[str, Any]) -> str:
    return str(record.get("ordkl") or "").split("<", 1)[0].strip().casefold()


def classes_from_head(head: str) -> tuple[str, ...]:
    """Return every word class explicitly expressed by a SAOL ordkl head.

    Matching is structural: abbreviations such as ``v.`` and ``s.`` must occur
    as standalone head tokens, so text like ``adverbiellt`` cannot accidentally
    become VERB.  Order follows the printed head where that matters only
    indirectly; callers should treat the result as a set of roles.
    """

    classes: list[str] = []

    def add(upos: str) -> None:
        if upos not in classes:
            classes.append(upos)

    if re.search(r"(?:^|\s)(?:subst\.|substantiv|s\.)(?=\s|$)", head):
        add("NOUN")
    if re.search(r"(?:^|\s)(?:verb|v\.|rxv|ptv)(?=\s|$)", head):
        add("VERB")
    if re.search(r"(?:^|\s)(?:adj\.|adjektiv)(?=\s|$)", head):
        add("ADJ")
    if re.search(r"(?:^|\s)adv\.(?=\s|$)", head) or re.search(r"\badverbiellt\b", head):
        add("ADV")
    if re.search(r"(?:^|\s)pron\.(?=\s|$)", head):
        add("PRON")
    if re.search(r"(?:^|\s)(?:räkn\.|räkneord)(?=\s|$)", head):
        add("NUM")
    if re.search(r"(?:^|\s)namn(?=\s|$)", head):
        add("PROPN")
    if re.search(r"(?:^|\s)interj\.(?=\s|$)", head):
        add("INTJ")
    if re.search(r"(?:^|\s)prep\.(?=\s|$)", head):
        add("ADP")
    if re.search(r"(?:^|\s)(?:konj\.|samordnande)(?=\s|$)", head):
        add("CCONJ")
    if re.search(r"(?:^|\s)(?:subj\.|underordnande)(?=\s|$)", head):
        add("SCONJ")

    return tuple(classes)


def classes_from_record(record: dict[str, Any]) -> tuple[str, ...]:
    classes = classes_from_head(ordkl_head(record))
    if classes:
        return classes
    fallback = str(record.get("upos") or "").strip().upper()
    return (fallback,) if fallback else ()


def record_for_class(record: dict[str, Any], target_upos: str) -> dict[str, Any]:
    """Return a class-specific view of a possibly mixed SAOL row.

    SAOL puts the inflection notation after the whole mixed head.  In the only
    inflected mixed family in SAOL14, ``adv. och adj. +t +a``, that notation
    belongs to the adjective role.  The adverb role is the printed lemma only.
    Other mixed heads in the current corpus have no inflection text.
    """

    copied = dict(record)
    head = ordkl_head(record)
    classes = set(classes_from_head(head))
    if target_upos not in classes:
        return copied

    # Give downstream single-class interpreters an unambiguous head.
    copied["upos"] = target_upos
    copied["ordkl"] = {
        "NOUN": "s.",
        "VERB": "v.",
        "ADJ": "adj.",
        "ADV": "adv.",
        "PRON": "pron.",
        "NUM": "räkn.",
        "ADP": "prep.",
        "SCONJ": "subj.",
        "CCONJ": "konj.",
        "INTJ": "interj.",
        "PROPN": "namn",
    }.get(target_upos, str(record.get("ordkl") or ""))

    if classes == {"ADJ", "ADV"} and target_upos == "ADV":
        # +t/+a belongs to the adjective reading; the adverb is invariant.
        copied["text"] = None

    return copied
